from .base_conv import MyBaseConv, MyBaseConvTranspose
from keras import saving


@saving.register_keras_serializable(package="MyConv", name="Conv3D")
class Conv3D(MyBaseConv):
    """3D convolution layer.

    This layer creates a convolution kernel that is convolved with the layer
    input over a 3D spatial (or temporal) dimension (width,height and depth) to
    produce a tensor of outputs. If `use_bias` is True, a bias vector is created
    and added to the outputs. Finally, if `activation` is not `None`, it is
    applied to the outputs as well.

    Args:
        filters: int, the dimension of the output space (the number of filters
            in the convolution).
        kernel_size: int or tuple/list of 3 integer, specifying the size of the
            convolution window.
        strides: int or tuple/list of 3 integer, specifying the stride length
            of the convolution. `strides > 1` is incompatible with
            `dilation_rate > 1`.
        padding: string, either `"valid"` or `"same"` (case-insensitive).
            `"valid"` means no padding. `"same"` results in padding evenly to
            the left/right or up/down of the input. When `padding="same"` and
            `strides=1`, the output has the same size as the input.
        data_format: string, either `"channels_last"` or `"channels_first"`.
            The ordering of the dimensions in the inputs. `"channels_last"`
            corresponds to inputs with shape
            `(batch_size, spatial_dim1, spatial_dim2, spatial_dim3, channels)`
            while `"channels_first"` corresponds to inputs with shape
            `(batch_size, channels, spatial_dim1, spatial_dim2, spatial_dim3)`.
            It defaults to the `image_data_format` value found in your Keras
            config file at `~/.keras/keras.json`. If you never set it, then it
            will be `"channels_last"`.
        dilation_rate: int or tuple/list of 3 integers, specifying the dilation
            rate to use for dilated convolution.
        groups: A positive int specifying the number of groups in which the
            input is split along the channel axis. Each group is convolved
            separately with `filters // groups` filters. The output is the
            concatenation of all the `groups` results along the channel axis.
            Input channels and `filters` must both be divisible by `groups`.
        activation: Activation function. If `None`, no activation is applied.
        use_bias: bool, if `True`, bias will be added to the output.
        kernel_initializer: Initializer for the convolution kernel. If `None`,
            the default initializer (`"glorot_uniform"`) will be used.
        bias_initializer: Initializer for the bias vector. If `None`, the
            default initializer (`"zeros"`) will be used.
        kernel_regularizer: Optional regularizer for the convolution kernel.
        bias_regularizer: Optional regularizer for the bias vector.
        activity_regularizer: Optional regularizer function for the output.
        kernel_constraint: Optional projection function to be applied to the
            kernel after being updated by an `Optimizer` (e.g. used to implement
            norm constraints or value constraints for layer weights). The
            function must take as input the unprojected variable and must return
            the projected variable (which must have the same shape). Constraints
            are not safe to use when doing asynchronous distributed training.
        bias_constraint: Optional projection function to be applied to the
            bias after being updated by an `Optimizer`.

    Input shape:

    - If `data_format="channels_last"`:
        5D tensor with shape:
        `(batch_size, spatial_dim1, spatial_dim2, spatial_dim3, channels)`
    - If `data_format="channels_first"`:
        5D tensor with shape:
        `(batch_size, channels, spatial_dim1, spatial_dim2, spatial_dim3)`

    Output shape:

    - If `data_format="channels_last"`:
        5D tensor with shape:
        `(batch_size, new_spatial_dim1, new_spatial_dim2, new_spatial_dim3,
        filters)`
    - If `data_format="channels_first"`:
        5D tensor with shape:
        `(batch_size, filters, new_spatial_dim1, new_spatial_dim2,
        new_spatial_dim3)`

    Returns:
        A 5D tensor representing `activation(conv3d(inputs, kernel) + bias)`.

    Raises:
        ValueError: when both `strides > 1` and `dilation_rate > 1`.

    Example:

    >>> x = np.random.rand(4, 10, 10, 10, 128)
    >>> y = keras.layers.Conv3D(32, 3, activation='relu')(x)
    >>> print(y.shape)
    (4, 8, 8, 8, 32)
    """

    def __init__(
        self,
        filters,
        kernel_size,
        strides=(1, 1, 1),
        padding="valid",
        data_format=None,
        dilation_rate=(1, 1, 1),
        groups=1,
        activation=None,
        use_bias=True,
        kernel_initializer="glorot_uniform",
        bias_initializer="zeros",
        kernel_regularizer=None,
        bias_regularizer=None,
        activity_regularizer=None,
        kernel_constraint=None,
        bias_constraint=None,
        **kwargs
    ):
        super().__init__(
            rank=3,
            filters=filters,
            kernel_size=kernel_size,
            strides=strides,
            padding=padding,
            data_format=data_format,
            dilation_rate=dilation_rate,
            groups=groups,
            activation=activation,
            use_bias=use_bias,
            kernel_initializer=kernel_initializer,
            bias_initializer=bias_initializer,
            kernel_regularizer=kernel_regularizer,
            bias_regularizer=bias_regularizer,
            activity_regularizer=activity_regularizer,
            kernel_constraint=kernel_constraint,
            bias_constraint=bias_constraint,
            **kwargs
        )

    

@saving.register_keras_serializable(package="MyConv", name="Conv3DTranspose")
class Conv3DTranspose(MyBaseConvTranspose):
    """3D transposed convolution layer.

    The need for transposed convolutions generally arise from the desire to use
    a transformation going in the opposite direction of a normal convolution,
    i.e., from something that has the shape of the output of some convolution
    to something that has the shape of its input while maintaining a
    connectivity pattern that is compatible with said convolution.

    Args:
        filters: int, the dimension of the output space (the number of filters
            in the transposed convolution).
        kernel_size: int or tuple/list of 1 integer, specifying the size of the
            transposed convolution window.
        strides: int or tuple/list of 1 integer, specifying the stride length
            of the transposed convolution. `strides > 1` is incompatible with
            `dilation_rate > 1`.
        padding: string, either `"valid"` or `"same"` (case-insensitive).
            `"valid"` means no padding. `"same"` results in padding evenly to
            the left/right or up/down of the input. When `padding="same"` and
            `strides=1`, the output has the same size as the input.
        data_format: string, either `"channels_last"` or `"channels_first"`.
            The ordering of the dimensions in the inputs. `"channels_last"`
            corresponds to inputs with shape
            `(batch_size, spatial_dim1, spatial_dim2, spatial_dim3, channels)`
            while `"channels_first"` corresponds to inputs with shape
            `(batch_size, channels, spatial_dim1, spatial_dim2, spatial_dim3)`.
            It defaults to the `image_data_format` value found in your Keras
            config file at `~/.keras/keras.json`. If you never set it, then it
            will be `"channels_last"`.
        dilation_rate: int or tuple/list of 1 integers, specifying the dilation
            rate to use for dilated transposed convolution.
        activation: Activation function. If `None`, no activation is applied.
        use_bias: bool, if `True`, bias will be added to the output.
        kernel_initializer: Initializer for the convolution kernel. If `None`,
            the default initializer (`"glorot_uniform"`) will be used.
        bias_initializer: Initializer for the bias vector. If `None`, the
            default initializer (`"zeros"`) will be used.
        kernel_regularizer: Optional regularizer for the convolution kernel.
        bias_regularizer: Optional regularizer for the bias vector.
        activity_regularizer: Optional regularizer function for the output.
        kernel_constraint: Optional projection function to be applied to the
            kernel after being updated by an `Optimizer` (e.g. used to implement
            norm constraints or value constraints for layer weights). The
            function must take as input the unprojected variable and must return
            the projected variable (which must have the same shape). Constraints
            are not safe to use when doing asynchronous distributed training.
        bias_constraint: Optional projection function to be applied to the
            bias after being updated by an `Optimizer`.

    Input shape:

    - If `data_format="channels_last"`:
        5D tensor with shape:
        `(batch_size, spatial_dim1, spatial_dim2, spatial_dim3, channels)`
    - If `data_format="channels_first"`:
        5D tensor with shape:
        `(batch_size, channels, spatial_dim1, spatial_dim2, spatial_dim3)`

    Output shape:

    - If `data_format="channels_last"`:
        5D tensor with shape:
        `(batch_size, new_spatial_dim1, new_spatial_dim2, new_spatial_dim3,
        filters)`
    - If `data_format="channels_first"`:
        5D tensor with shape:
        `(batch_size, filters, new_spatial_dim1, new_spatial_dim2,
        new_spatial_dim3)`

    Returns:
        A 5D tensor representing `activation(conv3d(inputs, kernel) + bias)`.

    Raises:
        ValueError: when both `strides > 1` and `dilation_rate > 1`.

    References:
    - [A guide to convolution arithmetic for deep learning](
        https://arxiv.org/abs/1603.07285v1)
    - [Deconvolutional Networks](
        https://www.matthewzeiler.com/mattzeiler/deconvolutionalnetworks.pdf)

    Example:

    >>> x = np.random.rand(4, 10, 8, 12, 128)
    >>> y = keras.layers.Conv3DTranspose(32, 2, 2, activation='relu')(x)
    >>> print(y.shape)
    (4, 20, 16, 24, 32)
    """

    def __init__(
        self,
        filters,
        kernel_size,
        strides=(1, 1, 1),
        padding="valid",
        data_format=None,
        dilation_rate=(1, 1, 1),
        activation=None,
        use_bias=True,
        kernel_initializer="glorot_uniform",
        bias_initializer="zeros",
        kernel_regularizer=None,
        bias_regularizer=None,
        activity_regularizer=None,
        kernel_constraint=None,
        bias_constraint=None,
        **kwargs
    ):
        super().__init__(
            rank=3,
            filters=filters,
            kernel_size=kernel_size,
            strides=strides,
            padding=padding,
            data_format=data_format,
            dilation_rate=dilation_rate,
            activation=activation,
            use_bias=use_bias,
            kernel_initializer=kernel_initializer,
            bias_initializer=bias_initializer,
            kernel_regularizer=kernel_regularizer,
            bias_regularizer=bias_regularizer,
            activity_regularizer=activity_regularizer,
            kernel_constraint=kernel_constraint,
            bias_constraint=bias_constraint,
            **kwargs
        )
