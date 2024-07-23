from typing import Any, Iterable

from torch import Tensor, nn

CHANNELS_KERNEL = tuple[int, int]
LAYERS_ARGS = tuple[CHANNELS_KERNEL, ...]
BLOCK_ARGS = tuple[LAYERS_ARGS, ...]
UNSTRUCTURED_BLOCK_ARGS = list[int | list[int | tuple[int, int]]]


class ConvBlock(nn.Module):
    def __init__(self, in_ch: int, layers_args: LAYERS_ARGS) -> None:
        super().__init__()

        def get_conv_block(
                in_: int, out: int, kernel_size: int = 3
        ) -> nn.Module:
            padding = kernel_size // 2
            return nn.Sequential(
                nn.Conv2d(
                    in_,
                    out,
                    kernel_size=kernel_size,
                    padding=padding,
                    bias=False,
                ),
                nn.BatchNorm2d(out),
                nn.ReLU(inplace=True),
            )

        prev_ch = in_ch
        convs = []
        for out_channels, kernel_size in layers_args:
            convs += [
                get_conv_block(prev_ch, out_channels, kernel_size=kernel_size)
            ]
            prev_ch = out_channels
        self.convs = nn.ModuleList(convs)

    def forward(self, x: Tensor, **kwargs: dict[Any, Any]) -> Tensor:
        for layer in self.convs:
            x = layer(x)
        return x


class Down(nn.Module):
    def __init__(self, in_ch: int, layers_args: LAYERS_ARGS) -> None:
        super().__init__()
        self.maxpool_conv = nn.Sequential(
            nn.MaxPool2d(2),
            ConvBlock(in_ch=in_ch, layers_args=layers_args),
        )

    def forward(self, x: Tensor, **kwargs: dict[Any, Any]) -> Tensor:
        return self.maxpool_conv(x)  # type: ignore[no-any-return]


def get_output_channels(layers_args: LAYERS_ARGS) -> int:
    """Returning number of output channels from layer arguments."""
    return layers_args[-1][0]


class UnetEncoder(nn.Module):
    def __init__(
            self,
            n_channels: int,
            blocks_args: BLOCK_ARGS,
            *args: tuple[Any, ...],
            **kwargs: dict[Any, Any],
    ) -> None:
        super().__init__()
        self.n_channels = n_channels
        self.blocks_args = blocks_args

        conv_blocks: list[nn.Module] = [
            ConvBlock(in_ch=n_channels, layers_args=blocks_args[0])
        ]
        prev_ch = get_output_channels(blocks_args[0])
        for layers_args in blocks_args[1:]:
            conv_blocks += [Down(in_ch=prev_ch, layers_args=layers_args)]
            prev_ch = get_output_channels(layers_args)

        self.conv_blocks = nn.ModuleList(conv_blocks)

    def forward(
            self, x: Tensor, *args: Any, **kwargs: Any
    ) -> dict[str, Tensor | list[Tensor]]:
        activations = []
        for block in self.conv_blocks:
            x = block(x)
            activations.append(x)
        emb = activations[-1]
        return {"emb": emb, "activations": activations}

    def deepen_model(self, new_blocks_args: BLOCK_ARGS) -> None:
        conv_blocks = []
        prev_ch = get_output_channels(self.blocks_args[0])
        for layers_args in new_blocks_args:
            conv_blocks += [Down(in_ch=prev_ch, layers_args=layers_args)]
            prev_ch = get_output_channels(layers_args)
        self.conv_blocks.extend(conv_blocks)
        self.blocks_args += new_blocks_args

    def get_hyperparameters(self) -> dict[str, Any]:
        return dict(
            n_channels=self.n_channels,
            blocks_args=self.blocks_args,
        )


def standarize_blocks_args(
        blocks_args: UNSTRUCTURED_BLOCK_ARGS,
        default_kernel_size: int = 3,
) -> BLOCK_ARGS:
    def decode_layer_args(layer_args: int | tuple[int, int]) -> CHANNELS_KERNEL:
        if isinstance(layer_args, int):
            return (layer_args, default_kernel_size)
        else:
            return layer_args

    def decode_multi_layer_args(
            multi_layer_args: int | Iterable[int | tuple[int, int]]
    ) -> LAYERS_ARGS:
        if isinstance(multi_layer_args, int):
            return ((multi_layer_args, default_kernel_size),)
        elif isinstance(multi_layer_args, Iterable):
            return tuple(
                decode_layer_args(layer_args) for layer_args in multi_layer_args
            )
        else:
            raise ValueError(
                f"Expected int or Iterable but got {multi_layer_args}."
            )

    final_blocks = tuple(
        decode_multi_layer_args(multi_layer_args)
        for multi_layer_args in blocks_args
    )
    return final_blocks
