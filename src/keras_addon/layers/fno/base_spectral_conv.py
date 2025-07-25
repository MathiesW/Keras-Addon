from keras import Layer
from keras import initializers
from keras import regularizers
from keras import constraints
from keras import ops
from keras.src.layers.input_spec import InputSpec
from keras.src.backend.config import backend
from keras.src.backend import standardize_data_format
from keras.src.utils.argument_validation import standardize_tuple
from importlib import import_module
from functools import partial


class BaseSpectralConv(Layer):
    def __init__(
        self,
        rank,
        filters,
        modes,
        data_format="channels_last",
        use_bias=True,
        kernel_initializer="he_normal",
        bias_initializer="zeros",
        kernel_constraint=None,
        bias_constraint=None,
        kernel_regularizer=None,
        bias_regularizer=None,
        name=None,
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.rank = rank
        self.filters = filters
        self.modes = standardize_tuple(modes, rank, name="modes")
        self.use_bias = use_bias
        self.kernel_initializer = initializers.get(kernel_initializer)
        self.bias_initializer = initializers.get(bias_initializer)
        self.kernel_regularizer = regularizers.get(kernel_regularizer)
        self.bias_regularizer = regularizers.get(bias_regularizer)
        self.kernel_constraint = constraints.get(kernel_constraint)
        self.bias_constraint = constraints.get(bias_constraint)
        self.data_format = standardize_data_format(data_format)

        fft_module = import_module(name="...ops.fft", package=__package__)
        self.rfft_fn = getattr(fft_module, "rfft" if self.rank == 1 else f"rfft{self.rank}")
        self.irfft_fn = getattr(fft_module, "irfft" if self.rank == 1 else f"irfft{self.rank}")

        # checks
        if self.filters is not None and self.filters <= 0:
            raise ValueError(
                "Invalid value for argument `filters`. Expected a strictly "
                f"positive value. Received filters={self.filters}."
            )
        
        if not all(self.modes):
            raise ValueError(
                "The argument `modes` cannot contain 0. Received "
                f"modes={self.modes}."
            )
        
        if self.data_format == "channels_first":
            raise NotImplementedError(
                "Data format 'channels_first' is currently not supported."
                "\nNVIDIA recommends to use 'channels_last' anyway! Deal with it!"
            )

    def build(self, input_shape):
        if self.built:
            return

        # get data axes
        if self.data_format == "channels_last":
            channel_axis = -1
            input_channel = input_shape[-1]

            # if data format is `"channels_last"`, we have to transpose in order to apply the rfft and irfft along the last axes
            axes = list(range(len(input_shape)))
            transpose_axes = axes.copy()
            inverse_transpose_axes = axes.copy()

            transpose_axes.insert(1, transpose_axes.pop(-1))
            inverse_transpose_axes.append(inverse_transpose_axes.pop(1))

            self.transpose_op = partial(ops.transpose, axes=transpose_axes)
            self.inverse_transpose_op = partial(ops.transpose, axes=inverse_transpose_axes)

        else:
            # NOTE this does not matter too much since currently the layer is restricted to use `"channels_last"` data format!
            channel_axis = 1
            input_channel = input_shape[1]

            # if data format is already `"channels_first"`, we do not have to transpose in order to apply the rfft and irfft
            self.transpose_op = lambda x: x
            self.inverse_transpose_op = lambda x: x

        # check pad with
        self.pad_width = (
                (0, 0),
                (0, 0), 
                *[(0, s // 2 + 1 - m if i == (len(self.modes) - 1) else s - m) for i, (m, s) in enumerate(zip(self.modes, input_shape[(1 if self.data_format == "channels_last" else 2):]))]
            )
        if list(filter(lambda x: x < (0, 0), self.pad_width)):
                raise ValueError("Too many modes for input shape!")
        
        self.input_spec = InputSpec(
            min_ndim=self.rank + 2, axes={channel_axis: input_channel}
        )

        kernel_shape = (input_channel, self.filters, *self.modes)

        # define real- and imaginary weights
        self._real_kernel = self.add_weight(
            name="real_kernel",
            shape=kernel_shape,
            initializer=self.kernel_initializer,
            regularizer=self.kernel_regularizer,
            constraint=self.kernel_constraint,
            trainable=True,
            dtype=self.dtype
        )
        self._imag_kernel = self.add_weight(
            name="imag_kernel",
            shape=kernel_shape,
            initializer=self.kernel_initializer,
            regularizer=self.kernel_regularizer,
            constraint=self.kernel_constraint,
            trainable=True,
            dtype=self.dtype
        )

        if self.use_bias:
            self.bias = self.add_weight(
                name="bias",
                shape=(self.filters,) + (1,) * self.rank,
                initializer=self.bias_initializer,
                regularizer=self.bias_regularizer,
                constraint=self.bias_constraint,
                trainable=True,
                dtype=self.dtype
            )
        else:
            self.bias = None

        """
        The layer operates in the complex Fourier space.
        Here, it is always `data_format="channels_first"`, such that the RFFT can be applied along the last axis or axes.

        Now, we need a slice object to truncate the mode / reduce the complex data to the relevant modes.
        The first two dimensions are the batch and the channel/filters. Then come the modes.

        In 1-D, the RFFT output is just `[0, *positive_freqs]`, shape is `(batch, channels, n // 2 + 1)`.

        In 2-D, we have a 2-D output with shape `(batch, channels, n, n // 2 + 1)`,
        because we have only positive frequencies in `x` but the full spectrum in `y`.

        we can apply an fftshift along the first feature dimension, which would make things way easier!
        In `y`-direction, we will then have `[*negative_freqs, 0, *positive_freqs]`.

        Note that the modes have to be doubled in order to see `m` positive and negative modes!

        """
        feature_axes = axes.copy()
        feature_axes.pop(0)  # remove batch dimension
        feature_axes.pop(channel_axis)  # -1 if self.data_format == "channels_last" else 1)  # remove channel dimension

        self.feature_dims = tuple(input_shape[a] for a in feature_axes)

        # self.fft_shift = lambda x: ops.roll()
        self.mode_truncation_slice = tuple([slice(None), slice(None), *[slice(None, m) for m in self.modes]])

        # declare einsum operation to apply weights
        einsum_dim = "".join([d for _, d in zip(self.modes, ["X", "Y", "Z"])])  # einsum dimensions are just letters for each mode, i.e., "XY" for modes=(8, 16)
        self.einsum_op_forward = f"bi{einsum_dim},io{einsum_dim}->bo{einsum_dim}"

        if backend == "tensorflow":
            # Backpropagation with `tensorflow` backend is a bit cumbersome and requires the exact gradient flow.
            # Therefore, we must declare additional `einsum_ops`.
            self.einsum_op_backprop_weights = f"bo{einsum_dim},bi{einsum_dim}->io{einsum_dim}"
            self.einsum_op_backprop_x = f"bo{einsum_dim},io{einsum_dim}->bi{einsum_dim}"
            self.einsum_op_backprop_bias = f"bo{einsum_dim}->o"  # sum over all axis except output channels

        self.built = True

    def rfft(self, x):
        """
        Performs fast Fourier transform on the real-valued `inputs`.
        
        Parameters
        ----------
        inputs : KerasTensor
            Real-valued input tensor.
        
        Returns
        -------
        (y_real, y_imag) : (KerasTensor, KerasTensor)
            Real- and imaginary part of fast Fourier tranform applied to `inputs`.

        Notes
        -----
        `inputs` must be of shape `(batch, channels, *features)`.

        """
        
        x = self.transpose_op(x)
        x_real, x_imag = self.rfft_fn(x)

        # # scale outputs for numerical stability in Fourier space
        # x_real /= self.rfft_scaling
        # x_imag /= self.rfft_scaling

        return x_real, x_imag
    
    def irfft(self, inputs):
        """
        Performs inverse fast Fourier transform on the `inputs`.
        
        Parameters
        ----------
        inputs : tuple
            Tuple of `KerasTensor` (real and imaginary part).
        
        Returns
        -------
        outputs : KerasTensor
            Real-valued output of inverse fast Fourier transform applied to `inputs`.

        Notes
        -----
        `inputs` must be of shape `((batch, channels, *features), (batch, channels, *features))`.

        """

        x_real, x_imag = inputs
        y_real = self.irfft_fn((x_real, x_imag))

        # # scale back to "normal" scale
        # y_real *= self.rfft_scaling

        return self.inverse_transpose_op(y_real)

    def rfft_shift(self, inputs):
        """
        Shifts the Fourier transformed data about `modes` in all directions except `x`.

        Parameters
        ----------
        inputs : KerasTensor
            Real-valued input tensor.

        shifted_inputs : KerasTensor
            Shifted version of `inputs`

        """
        
        shape = ops.ndim(inputs)

        for a, m in zip(range(len(self.modes), shape - 1), self.modes):
            inputs = ops.roll(inputs, shift=-m // 2, axis=a)

        return inputs
    
    def call(self, inputs):
        if backend() == "tensorflow":
            """
            
            Parameters
            ----------
            inputs : KerasTensor
                Input to `SpectralConv1D` layer.

            Returns
            -------
            (y, grad) : (KerasTensor, callable)
                Tuple of the output of `SpectralConv1D` and the gradient.

            """

            @ops.custom_gradient
            def forward(inputs):
                """
                Custom gradient for `tensorflow` backend
            
                Parameters
                ----------
                inputs : KerasTensor
                    Input to `SpectralConv1D` layer.

                Returns
                -------
                (y, grad) : (KerasTensor, callable)
                    Tuple of the output of `SpectralConv1D` and the gradient.
                    
                """
                
                x_hat_real, x_hat_imag = self.rfft(inputs)  # shape = (None, ch_in, *dims), where dims = [nx // 2 + 1] for 1-D and [ny, nx // 2 + 1] for 2-D

                # apply fft shift
                x_hat_real = self.rfft_shift(x_hat_real)
                x_hat_imag = self.rfft_shift(x_hat_imag)

                # reduce to relevant modes
                x_hat_real_truncated = x_hat_real[self.mode_truncation_slice]  # shape = (None, ch_in, *m)
                x_hat_imag_truncated = x_hat_imag[self.mode_truncation_slice]  # shape = (None, ch_in, *m)

                y_hat_real_truncated = ops.einsum(self.einsum_op_forward, x_hat_real_truncated, self._real_kernel) - ops.einsum(self.einsum_op_forward, x_hat_imag_truncated, self._imag_kernel)
                y_hat_imag_truncated = ops.einsum(self.einsum_op_forward, x_hat_real_truncated, self._real_kernel) - ops.einsum(self.einsum_op_forward, x_hat_imag_truncated, self._imag_kernel)

                y_hat_real = ops.pad(y_hat_real_truncated, pad_width=self.pad_width)  # shape = (None, ch_out, *n)
                y_hat_imag = ops.pad(y_hat_imag_truncated, pad_width=self.pad_width)  # shape = (None, ch_out, *n)

                # add bias, shape = (None, ch_out, *m)
                if self.use_bias:
                    y_hat_real += self.bias
                    y_hat_imag += self.bias

                # apply ifft shift
                y_hat_real = self.rfft_shift(y_hat_real)
                y_hat_imag = self.rfft_shift(y_hat_imag)

                # reconstruct y via irfft
                y = self.irfft((y_hat_real, y_hat_imag))  # shape = (None, *input_dims, ch_out)

                def backprop(dy, variables=None):
                    """
                    Backpropagation through the `SpectralConv1D` layer

                    Parameters
                    ----------
                    dy : KerasTensor
                        Gradient of `y`.
                    variables : list, optional
                        List of variables.
                        Defaults to `None`

                    Returns
                    -------
                    (dx, dw) : (KerasTensor, list)
                        Tuple of the gradient of `x` and a list containing the gradients of the weights.
                    
                    """

                    # get real and imaginary part via rfft, shape = (None, x//2+1, ch_out)
                    dy_hat_real, dy_hat_imag = self.rfft(dy)
                    
                    # apply fft shift
                    dy_hat_real = self.rfft_shift(dy_hat_real)
                    dy_hat_imag = self.rfft_shift(dy_hat_imag)

                    # reduce to relevant modes, shape = (None, m, ch_out)
                    dy_hat_real_truncated = dy_hat_real[self.mode_truncation_slice]
                    dy_hat_imag_truncated = dy_hat_imag[self.mode_truncation_slice]

                    # compute gradients for weights, shape = (ch_in, m, ch_out)
                    dw_real = ops.einsum(self.einsum_op_backprop_weights, dy_hat_real_truncated, x_hat_real_truncated) + ops.einsum(self.einsum_op_backprop_weights, dy_hat_imag_truncated, x_hat_imag_truncated)
                    dw_imag = ops.einsum(self.einsum_op_backprop_weights, dy_hat_real_truncated, x_hat_imag_truncated) - ops.einsum(self.einsum_op_backprop_weights, dy_hat_imag_truncated, x_hat_real_truncated)

                    if self.use_bias:
                        # compute gradients for bias, shape = (ch_out, )
                        db = ops.einsum(self.einsum_op_backprop_bias, dy_hat_real_truncated + dy_hat_imag_truncated)

                    # compute gradient for inputs, shape = (None, m, ch_in)
                    dx_hat_real_truncated = ops.einsum(self.einsum_op_backprop_x, dy_hat_real_truncated, self._real_kernel) + ops.einsum(self.einsum_op_backprop_x, dy_hat_imag_truncated, self._imag_kernel)
                    dx_hat_imag_truncated = ops.einsum(self.einsum_op_backprop_x, dy_hat_imag_truncated, self._real_kernel) - ops.einsum(self.einsum_op_backprop_x, dy_hat_real_truncated, self._imag_kernel)

                    # pad for ifft, shape = (None, x, ch_in)
                    dx_hat_real = ops.pad(dx_hat_real_truncated, pad_width=self.pad_width)
                    dx_hat_imag = ops.pad(dx_hat_imag_truncated, pad_width=self.pad_width)

                    # apply ifft shift
                    dx_hat_real = self.rfft_shift(dx_hat_real)
                    dx_hat_imag = self.rfft_shift(dx_hat_imag)

                    # apply irfft, shape = (None, x, ch_in)
                    dx = self.irfft((dx_hat_real, dx_hat_imag))
                    if self.use_bias:
                        return dx, [db, dw_real, dw_imag]
                    
                    return dx, [dw_real, dw_imag]

                return y, backprop
                
            return forward(inputs)

        if backend() == "jax":
            """
            
            Parameters
            ----------
            inputs : KerasTensor
                Input to `SpectralConv1D` layer.

            Returns
            -------
            y : KerasTensor
                The output of `SpectralConv1D`.

            """

            # forward pass, shape = (None, x, y, ch_in)
            x_hat_real, x_hat_imag = self.rfft(inputs)

            # apply fft shift
            x_hat_real = self.rfft_shift(x_hat_real)
            x_hat_imag = self.rfft_shift(x_hat_imag)

            # reduce to relevant modes, shape = (None, mx, my, ch_in)
            x_hat_real_reduced = x_hat_real[self.mode_truncation_slice]  # 1D: (batch, m, ch_out), 2D: (batch, mx, my, ch_in)
            x_hat_imag_reduced = x_hat_imag[self.mode_truncation_slice]  # 1D: (batch, m, ch_out), 2D: (batch, mx, my, ch_in)

            y_hat_real_truncated = ops.einsum(self.einsum_op_forward, x_hat_real_reduced, self._real_kernel) - ops.einsum(self.einsum_op_forward, x_hat_imag_reduced, self._imag_kernel)
            y_hat_imag_truncated = ops.einsum(self.einsum_op_forward, x_hat_real_reduced, self._real_kernel) - ops.einsum(self.einsum_op_forward, x_hat_imag_reduced, self._imag_kernel)

            y_hat_real = ops.pad(y_hat_real_truncated, pad_width=self.pad_width)
            y_hat_imag = ops.pad(y_hat_imag_truncated, pad_width=self.pad_width)

            # add bias, shape = (None, mx, my, ch_out)
            if self.use_bias:
                y_hat_real += self.bias
                y_hat_imag += self.bias

            # apply ifft shift
            y_hat_real = self.rfft_shift(y_hat_real)
            y_hat_imag = self.rfft_shift(y_hat_imag)

            # reconstruct y via irfft, shape = (None, x, y, ch_out)
            y = self.irfft((y_hat_real, y_hat_imag))

            return y

        raise NotImplementedError(f"The call method is only implemented for keras backends `'tensorflow'` and `'jax'`")

    def compute_output_shape(self, input_shape):
        """
        Compute output shape of `BaseSpectralConv`

        Parameters
        ----------
        input_shape : tuple
            Input shape.

        Returns
        -------
        output_shape : tuple
            Output shape.

        """

        input_shape: list = list(input_shape)
        channel_axis = -1 if self.data_format == 'channels_last' else 1

        input_shape[channel_axis] = self.filters
        return tuple(input_shape)

    def get_config(self):
        """
        Get config method.
        Required for serialization.

        Returns
        -------
        config : dict
            Dictionary with the configuration of `BaseSpectralConv`.

        Notes
        -----
        The `config` does not contain the `self.rank` parameter,
        which is not required when the class is subclassed with hard-coded `rank`.

        """
        
        config = super().get_config()
        config.update({
            "filters": self.filters,
            "modes": self.modes,
            "data_format": self.data_format,
            "use_bias": self.use_bias,
            "kernel_initializer": initializers.serialize(self.kernel_initializer),
            "bias_initializer": initializers.serialize(self.bias_initializer),
            "kernel_constraint": constraints.serialize(self.kernel_constraint),
            "bias_constraint": constraints.serialize(self.bias_constraint),
            "kernel_regularizer": regularizers.serialize(self.kernel_regularizer),
            "bias_regularizer": regularizers.serialize(self.bias_regularizer)
        })
        return config

    @classmethod
    def from_config(cls, config):
        """
        Necessary for Keras deserialization

        Parameters
        ----------
        cls : BasBaseSpectralConvFCN
            The `BaseSpectralConv` class.
        config : dict
            Dictionary with the layer configuration.

        Returns
        -------
        cls : BaseSpectralConv
            Instance of `BaseSpectralConv` from `config`.
            
        """

        kernel_initializer_cfg = config.pop("kernel_initialzer")
        bias_initializer_cfg = config.pop("bias_initialzer")
        kernel_constraint_cfg = config.pop("kernel_constraint")
        bias_constraint_cfg = config.pop("bias_constraint")
        kernel_regularizer_cfg = config.pop("kernel_regularizer")
        bias_regularizer_cfg = config.pop("bias_regularizer")

        config.update({
            "kernel_initializer": initializers.deserialize(kernel_initializer_cfg),
            "bias_initializer": initializers.deserialize(bias_initializer_cfg),
            "kernel_constraint": constraints.deserialize(kernel_constraint_cfg),
            "bias_constraint": constraints.deserialize(bias_constraint_cfg),
            "kernel_regularizer": regularizers.deserialize(kernel_regularizer_cfg),
            "bias_regularizer": regularizers.deserialize(bias_regularizer_cfg)
        })

        return cls(**config)
