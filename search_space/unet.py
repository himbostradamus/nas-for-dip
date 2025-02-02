from collections import OrderedDict
import torch
import nni.retiarii.nn.pytorch as nn
from nni import trace
from nni.retiarii import model_wrapper
from nni.retiarii.nn.pytorch import Cell

@trace
def conv_2d(C_in, C_out, kernel_size=3, dilation=1, padding=1, activation=None):
    return nn.Sequential(
        nn.Conv2d(C_in, C_out, kernel_size=kernel_size, dilation=dilation, padding=padding, bias=False),
        nn.BatchNorm2d(C_out),
        nn.ReLU() if activation is None else activation,
    )

@trace
def depthwise_separable_conv(C_in, C_out, kernel_size=3, dilation=1, padding=1, activation=None):
    return nn.Sequential(
        nn.Conv2d(C_in, C_in, kernel_size=kernel_size, dilation=dilation, padding=padding, groups=C_in, bias=False),
        nn.Conv2d(C_in, C_out, 1, bias=False),
        nn.BatchNorm2d(C_out),
        nn.ReLU() if activation is None else activation,
    )

@trace
def transposed_conv_2d(C_in, C_out, kernel_size=4, stride=2, padding=1, activation=None):
    return nn.Sequential(
        nn.ConvTranspose2d(C_in, C_out, kernel_size=kernel_size, stride=stride, padding=padding, bias=False),
        nn.BatchNorm2d(C_out),
        nn.ReLU() if activation is None else activation
    )

@trace
def attention(channel, reduction=16):
    return nn.Sequential(
        nn.Linear(channel, channel // reduction, bias=False),
        nn.ReLU(inplace=True),
        nn.Linear(channel // reduction, channel, bias=False),
        nn.Sigmoid()
    )


def pools():
    pool_dict = OrderedDict([
        ("MaxPool2d", nn.MaxPool2d(kernel_size=2, stride=2, padding=0)),
        ("AvgPool2d", nn.AvgPool2d(kernel_size=2, stride=2, padding=0)),
        ("AdaMaxPool2d", nn.AdaptiveMaxPool2d(1)),
        ("AdaAvgPool2d", nn.AdaptiveAvgPool2d(1)),
        ("MaxPool2d_3x3", nn.MaxPool2d(kernel_size=3, stride=2, padding=1)),
        ("AvgPool2d_3x3", nn.AvgPool2d(kernel_size=3, stride=2, padding=1)),
        ("MaxPool2d_5x5", nn.MaxPool2d(kernel_size=5, stride=2, padding=2)),
        ("AvgPool2d_5x5", nn.AvgPool2d(kernel_size=5, stride=2, padding=2)),
        ("MaxPool2d_7x7", nn.MaxPool2d(kernel_size=7, stride=2, padding=3)),
        ("AvgPool2d_7x7", nn.AvgPool2d(kernel_size=7, stride=2, padding=3)),
        ("MaxPool2d_9x9", nn.MaxPool2d(kernel_size=9, stride=2, padding=4)),
        ("AvgPool2d_9x9", nn.AvgPool2d(kernel_size=9, stride=2, padding=4)),

        # ("DepthToSpace", nn.PixelShuffle(2)),
    ])
    return pool_dict

def upsamples(C_in, C_out):
    upsample_dict = OrderedDict([
        ("Upsample_nearest", nn.Upsample(scale_factor=2, mode='nearest')),
        ("Upsample_bilinear", nn.Upsample(scale_factor=2, mode='bilinear')),
        
        ("TransConv_2x2_RelU", transposed_conv_2d(C_in, C_out, kernel_size=2, stride=2, padding=0)),
        ("TransConv_2x2_SiLU", transposed_conv_2d(C_in, C_out, kernel_size=2, stride=2, padding=0, activation=nn.SiLU())),
        ("TransConv_2x2_Sigmoid", transposed_conv_2d(C_in, C_out, kernel_size=2, stride=2, padding=0, activation=nn.Sigmoid())),

        ("TransConv_4x4_Relu", transposed_conv_2d(C_in, C_out)),
        ("TransConv_4x4_SiLU", transposed_conv_2d(C_in, C_out, activation=nn.SiLU())),
        ("TransConv_4x4_Sigmoid", transposed_conv_2d(C_in, C_out, activation=nn.Sigmoid())),
        
    ])
    return upsample_dict

def convs(C_in, C_out):
    # all padding should follow this formula:
    # pd = (ks - 1) * dl // 2
    conv_dict = OrderedDict([
        
        # ("Identity", nn.Identity()),

        # ("conv2d_1x1_Relu", conv_2d(C_in, C_out, kernel_size=1, padding=0)),
        # ("conv2d_1x1_SiLU", conv_2d(C_in, C_out, kernel_size=1, padding=0, activation=nn.SiLU())),
        ("conv2d_1x1_Sigmoid", conv_2d(C_in, C_out, kernel_size=1, padding=0, activation=nn.Sigmoid())),
        ("conv2d_1x1_Mish", conv_2d(C_in, C_out, kernel_size=1, padding=0, activation=nn.Mish())),

        ("conv2d_3x3_Relu", conv_2d(C_in, C_out, kernel_size=3, padding=1)),
        # ("conv2d_3x3_SiLU", conv_2d(C_in, C_out, kernel_size=3, padding=1, activation=nn.SiLU())),
        # ("conv2d_3x3_Sigmoid", conv_2d(C_in, C_out, kernel_size=3, padding=1, activation=nn.Sigmoid())),
        ("conv2d_3x3_Mish", conv_2d(C_in, C_out, kernel_size=3, padding=1, activation=nn.Mish())),
        # ("conv2d_3x3_Relu_1dil", conv_2d(C_in, C_out, kernel_size=3, padding=2, dilation=2)),
        # ("conv2d_3x3_SiLU_1dil", conv_2d(C_in, C_out, kernel_size=3, padding=2, dilation=2, activation=nn.SiLU())),
        # ("conv2d_3x3_Sigmoid_1dil", conv_2d(C_in, C_out, kernel_size=3, padding=2, dilation=2, activation=nn.Sigmoid())),

        # ("conv2d_5x5_Relu", conv_2d(C_in, C_out, kernel_size=5, padding=2)),
        ("conv2d_5x5_SiLU", conv_2d(C_in, C_out, kernel_size=5, padding=2, activation=nn.SiLU())),
        # ("conv2d_5x5_Sigmoid", conv_2d(C_in, C_out, kernel_size=5, padding=2, activation=nn.Sigmoid())),
        # ("conv2d_5x5_Mish", conv_2d(C_in, C_out, kernel_size=5, padding=2, activation=nn.Mish())),
        # ("conv2d_5x5_Relu_1dil", conv_2d(C_in, C_out, kernel_size=5, padding=4, dilation=2, activation=nn.SiLU())),
        # ("conv2d_5x5_SiLU_1dil", conv_2d(C_in, C_out, kernel_size=5, padding=4, dilation=2, activation=nn.SiLU())),
        # ("conv2d_5x5_Sigmoid_1dil", conv_2d(C_in, C_out, kernel_size=5, padding=4, dilation=2, activation=nn.Sigmoid())),
        # ("conv2d_5x5_Mish_1dil", conv_2d(C_in, C_out, kernel_size=5, padding=4, dilation=2, activation=nn.Mish())),

        # ("conv2d_7x7_Relu", conv_2d(C_in, C_out, kernel_size=7, padding=3)),
        # ("conv2d_7x7_SiLU", conv_2d(C_in, C_out, kernel_size=7, padding=3, activation=nn.SiLU())),
        # ("conv2d_7x7_Sigmoid", conv_2d(C_in, C_out, kernel_size=7, padding=3, activation=nn.Sigmoid())),
        ("conv2d_7x7_Mish", conv_2d(C_in, C_out, kernel_size=7, padding=3, activation=nn.Mish())),
        # ("conv2d_7x7_Relu_1dil", conv_2d(C_in, C_out, kernel_size=7, padding=6, dilation=2, activation=nn.SiLU())),
        # ("conv2d_7x7_SiLU_1dil", conv_2d(C_in, C_out, kernel_size=7, padding=6, dilation=2, activation=nn.SiLU())),
        # ("conv2d_7x7_Sigmoid_1dil", conv_2d(C_in, C_out, kernel_size=7, padding=6, dilation=2, activation=nn.Sigmoid())),

        # ("conv2d_9x9_Relu", conv_2d(C_in, C_out, kernel_size=9, padding=4)),
        # ("conv2d_9x9_SiLU", conv_2d(C_in, C_out, kernel_size=9, padding=4, activation=nn.SiLU())),
        # ("conv2d_9x9_Sigmoid", conv_2d(C_in, C_out, kernel_size=9, padding=4, activation=nn.Sigmoid())),
        # ("conv2d_9x9_Mish", conv_2d(C_in, C_out, kernel_size=9, padding=4, activation=nn.Mish())),
        # ("conv2d_9x9_Relu_1dil", conv_2d(C_in, C_out, kernel_size=9, padding=8, dilation=2, activation=nn.SiLU())),
        # ("conv2d_9x9_SiLU_1dil", conv_2d(C_in, C_out, kernel_size=9, padding=8, dilation=2, activation=nn.SiLU())),
        # ("conv2d_9x9_Sigmoid_1dil", conv_2d(C_in, C_out, kernel_size=9, padding=8, dilation=2, activation=nn.Sigmoid())),

        # ("convDS_1x1_Relu", depthwise_separable_conv(C_in, C_out)),
        ("convDS_1x1_SiLU", depthwise_separable_conv(C_in, C_out, activation=nn.SiLU())),
        # ("convDS_1x1_Sigmoid", depthwise_separable_conv(C_in, C_out, activation=nn.Sigmoid())),
        # ("convDS_1x1_Mish", depthwise_separable_conv(C_in, C_out, activation=nn.Mish())),

        # ("convDS_3x3_Relu", depthwise_separable_conv(C_in, C_out, kernel_size=3, padding=1)),
        # ("convDS_3x3_SiLU", depthwise_separable_conv(C_in, C_out, kernel_size=3, padding=1, activation=nn.SiLU())),
        # ("convDS_3x3_Sigmoid", depthwise_separable_conv(C_in, C_out, kernel_size=3, padding=1, activation=nn.Sigmoid())),
        # ("convDS_3x3_Relu_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=3, padding=2, dilation=2)),
        # ("convDS_3x3_SiLU_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=3, padding=2, dilation=2, activation=nn.SiLU())),
        # ("convDS_3x3_Sigmoid_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=3, padding=2, dilation=2, activation=nn.Sigmoid())),

        # ("convDS_5x5_Relu", depthwise_separable_conv(C_in, C_out, kernel_size=5, padding=2)),
        # ("convDS_5x5_SiLU", depthwise_separable_conv(C_in, C_out, kernel_size=5, padding=2, activation=nn.SiLU())),
        # ("convDS_5x5_Sigmoid", depthwise_separable_conv(C_in, C_out, kernel_size=5, padding=2, activation=nn.Sigmoid())),
        ("convDS_5x5_Mish", depthwise_separable_conv(C_in, C_out, kernel_size=5, padding=2, activation=nn.Mish())),
        # ("convDS_5x5_Relu_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=5, padding=4, dilation=2, activation=nn.SiLU())),
        # ("convDS_5x5_SiLU_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=5, padding=4, dilation=2, activation=nn.SiLU())),
        # ("convDS_5x5_Sigmoid_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=5, padding=4, dilation=2, activation=nn.Sigmoid())),

        # ("convDS_7x7_Relu", depthwise_separable_conv(C_in, C_out, kernel_size=7, padding=3)),
        # ("convDS_7x7_SiLU", depthwise_separable_conv(C_in, C_out, kernel_size=7, padding=3, activation=nn.SiLU())),
        # ("convDS_7x7_Sigmoid", depthwise_separable_conv(C_in, C_out, kernel_size=7, padding=3, activation=nn.Sigmoid())),
        # ("convDS_7x7_Relu_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=7, padding=6, dilation=2, activation=nn.SiLU())),
        # ("convDS_7x7_SiLU_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=7, padding=6, dilation=2, activation=nn.SiLU())),
        # ("convDS_7x7_Sigmoid_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=7, padding=6, dilation=2, activation=nn.Sigmoid())),

        # ("convDS_9x9_Relu", depthwise_separable_conv(C_in, C_out, kernel_size=9, padding=4)),
        # ("convDS_9x9_SiLU", depthwise_separable_conv(C_in, C_out, kernel_size=9, padding=4, activation=nn.SiLU())),
        # ("convDS_9x9_Sigmoid", depthwise_separable_conv(C_in, C_out, kernel_size=9, padding=4, activation=nn.Sigmoid())),
        # ("convDS_9x9_Relu_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=9, padding=8, dilation=2, activation=nn.SiLU())),
        # ("convDS_9x9_SiLU_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=9, padding=8, dilation=2, activation=nn.SiLU())),
        # ("convDS_9x9_Sigmoid_1dil", depthwise_separable_conv(C_in, C_out, kernel_size=9, padding=8, dilation=2, activation=nn.Sigmoid())),
    ])
    return conv_dict



class UNetBasic(torch.nn.Module):

    def __init__(self, in_channels=1, out_channels=1, init_features=32, depth=4):
        super(UNetBasic, self).__init__()

        self.depth = depth

        features = init_features
        self.pools = nn.ModuleList()
        self.encoders = nn.ModuleList()
        self.encoders.append(UNetBasic._block(in_channels, features, name="enc1"))
        self.pools.append(nn.MaxPool2d(kernel_size=2, stride=2))

        for i in range(depth-1):
            self.encoders.append(UNetBasic._block(features, features * 2, name=f"enc{i+2}"))
            self.pools.append(nn.MaxPool2d(kernel_size=2, stride=2))
            features *= 2

        self.bottleneck = UNetBasic._block(features, features * 2, name="bottleneck")

        self.upconvs = nn.ModuleList()
        self.decoders = nn.ModuleList()
        for i in range(depth):
            self.upconvs.append(nn.ConvTranspose2d(
                features * 2, features, kernel_size=2, stride=2
            ))
            self.decoders.append(UNetBasic._block(features * 2, features, name=f"dec{i+1}"))
            features //= 2
        

        self.conv = nn.Conv2d(
            in_channels=features*2, out_channels=out_channels, kernel_size=1
        )

    def forward(self, x):
        skips = []
        for i in range(self.depth):
            x = self.encoders[i](x)
            skips.append(x)
            x = self.pools[i](x)
            
        x = self.bottleneck(x)

        for i in range(self.depth):
            x = self.upconvs[i](x)
            x = torch.cat((x, skips[-i-1]), dim=1)
            x = self.decoders[i](x)
        return torch.sigmoid(self.conv(x))

    @staticmethod
    def _block(in_channels, features, name):
        return nn.Sequential(
            OrderedDict(
                [
                    (
                        name + "conv1",
                        nn.Conv2d(
                            in_channels=in_channels,
                            out_channels=features,
                            kernel_size=3,
                            padding=1,
                            bias=False,
                        ),
                    ),
                    (name + "norm1", nn.BatchNorm2d(num_features=features)),
                    (name + "relu1", nn.ReLU(inplace=True)),
                    (
                        name + "conv2",
                        nn.Conv2d(
                            in_channels=features,
                            out_channels=features,
                            kernel_size=3,
                            padding=1,
                            bias=False,
                        ),
                    ),
                    (name + "norm2", nn.BatchNorm2d(num_features=features)),
                    (name + "relu2", nn.ReLU(inplace=True)),
                ]
            )
        )
    
    def test(self):
        x = torch.randn(1, 1, 64, 64)
        out = self.forward(x)
        print(out.shape)
        assert out.shape == (1, 1, 64, 64)
        print('Test passed')

@trace
@model_wrapper
class UNetSpace(nn.Module):
    def __init__(
            self, 
            C_in=1, 
            C_out=1, 
            depth=2, 
            nodes_per_layer=1, # accept only 1 or 2,
            ops_per_node=1,
            poolOps_per_node=1,
            upsampleOps_per_node=1,
            use_attention=False
            
            ):
        super().__init__()

        self.depth = depth
        self.nodes = nodes_per_layer
        nodes = nodes_per_layer
        self.use_attention = use_attention
        

        # encoder layers
        end_filters = 64
        mid_in = 64
        self.pools = nn.ModuleList()
        self.preencoders = nn.ModuleList()
        self.encoders = nn.ModuleList()
        self.postencoders = nn.ModuleList()
        self.enAttentions = nn.ModuleList()

        self.preencoders.append(nn.Conv2d(C_in, mid_in, kernel_size=3, padding=1))
        self.encoders.append(Cell(
                op_candidates=convs(mid_in,mid_in),
                num_nodes=1,
                num_ops_per_node=ops_per_node,
                num_predecessors=1,
                label=f"encoder 1"
            ))
        self.enAttentions.append(attention(mid_in,16))
        self.pools.append(Cell(
                op_candidates=pools(),
                num_nodes=1, 
                num_ops_per_node=poolOps_per_node,
                num_predecessors=1, 
                label=f"pool 1"
            ))

        for i in range(self.depth-1):
            self.pools.append(Cell(
                op_candidates=pools(),
                num_nodes=1,
                num_ops_per_node=poolOps_per_node,
                num_predecessors=1,
                label=f"pool {i+2}"
            ))
            
            if nodes == 1:
                self.preencoders.append(nn.Conv2d(mid_in, mid_in*2, kernel_size=3, padding=1))
                encoder_in_channels, encoder_out_channels = mid_in*2, mid_in*2
            else:
                encoder_in_channels, encoder_out_channels = mid_in, mid_in
                
            self.encoders.append(Cell(
                op_candidates=convs(encoder_in_channels, encoder_out_channels),
                num_nodes=nodes,
                num_ops_per_node=ops_per_node,
                num_predecessors=1,
                label=f"encoder {i+2}"
            ))

            self.enAttentions.append(attention(mid_in*2, 16))
            mid_in *= 2


        if nodes == 1:
            self.preencoders.append(nn.Conv2d(mid_in, mid_in*2, kernel_size=3, padding=1))
            encoder_in_channels, encoder_out_channels = mid_in*2, mid_in*2
        else:
            encoder_in_channels, encoder_out_channels = mid_in, mid_in
        self.bottleneck = Cell(
                op_candidates=convs(encoder_in_channels,encoder_out_channels),
                num_nodes=nodes,
                num_ops_per_node=ops_per_node,
                num_predecessors=1,
                label=f"bottleneck"
            )

        # decoder layers
        self.upsamples = nn.ModuleList()
        self.predecoders = nn.ModuleList()
        self.decoders = nn.ModuleList()
        self.postdecoders = nn.ModuleList()
        self.decAttentions = nn.ModuleList()
        for i in range(self.depth):
            self.upsamples.append(Cell(
                op_candidates=upsamples(mid_in,mid_in),
                num_nodes=1, 
                num_ops_per_node=upsampleOps_per_node,
                num_predecessors=1, 
                label=f"upsample {self.depth-i-1}"
            ))
            self.predecoders.append(nn.Conv2d(mid_in*3, mid_in, kernel_size=3, padding=1))
            self.decoders.append(Cell(
                op_candidates=convs(mid_in,mid_in),
                num_nodes=nodes, 
                num_ops_per_node=ops_per_node,
                num_predecessors=1, 
                label=f"decoder {self.depth-i-1}"
            ))
            self.decAttentions.append(attention(mid_in,16))
            mid_in //= 2

        self.out_layer = nn.Conv2d(end_filters, C_out, kernel_size=3, padding=1)
        
    def forward(self, x):
        print(f'input shape: {x.shape}')
        x = self.in_layer(x)
        print(f'after in_layer: {x.shape}')
        skip_connections = [x]

        for i in range(self.depth):
            x = self.pools[i]([x])
            x = self.preencoders[i](x)
            x = self.encoders[i]([x])
            if self.use_attention:
                x = self.attention_forward(x, self.enAttentions[i])
            skip_connections.append(x)

        for i in range(self.depth):
            upsampled = self.upsamples[i]([x])
            cropped = self.crop_tensor(upsampled, skip_connections[-(i+2)])
            x = torch.cat([cropped, upsampled], 1)
            x = self.predecoders[i](x)
            x = self.decoders[i]([x])
            if self.use_attention:
                x = self.attention_forward(x, self.decAttentions[i])

        x = self.out_layer(x)
        return x

    def crop_tensor(self, target_tensor, tensor):
        target_size = target_tensor.size()[2]  # Assuming height and width are same
        tensor_size = tensor.size()[2]
        delta = tensor_size - target_size
        delta = delta // 2
        return tensor[:, :, delta:tensor_size-delta, delta:tensor_size-delta]
    
    def attention_forward(self, x, fcs):
        b, c, _, _ = x.size()
        y = nn.AdaptiveAvgPool2d(1)(x).view(b, c)
        y = fcs(y).view(b, c, 1, 1)
        return x * y.expand_as(x)
    


class exportedModel(nn.Module):
    def __init__(self, C_in, C_out, depth, exported_arch):
        super().__init__()

        self.depth = depth
        start_filters = end_filters = 64
        self.in_layer = nn.Conv2d(C_in, start_filters, kernel_size=3, padding=1)

        mid_in = 64
        self.pools = nn.ModuleList()
        self.encoders = nn.ModuleList()
        self.postencoders = nn.ModuleList()
        self.enAttentions = nn.ModuleList()

        for i in range(depth):
            self.pools.append(pools()[exported_arch[f'pool {i}/op_1_0']])
            self.encoders.append(convs(mid_in, mid_in)[exported_arch[f'encoder {i}/op_1_0']])
            self.postencoders.append(nn.Conv2d(mid_in, mid_in*2, kernel_size=3, padding=1)) 
            self.encoders.append(nn.Conv2d(mid_in*2, mid_in*2, kernel_size=3, padding=1))
            self.enAttentions.append(attention(mid_in*2,16))
            mid_in *= 2

        
        # decoder layers
        self.upsamples = nn.ModuleList()
        self.predecoders = nn.ModuleList()
        self.decoders = nn.ModuleList()
        self.postdecoders = nn.ModuleList()
        self.decAttentions = nn.ModuleList()
        for i in range(self.depth):
            self.upsamples.append(upsamples(mid_in, mid_in)[exported_arch[f'upsample {i}/op_1_0']])
            mid_in //= 2
            self.predecoders.append(nn.Conv2d(mid_in*3, mid_in, kernel_size=3, padding=1))
            self.decoders.append(convs(mid_in, mid_in)[exported_arch[f'decoder {i}/op_1_0']])
            self.postdecoders.append(nn.Conv2d(mid_in, mid_in, kernel_size=3, padding=1))
            self.decAttentions.append(attention(mid_in,16))

        self.out_layer = nn.Conv2d(end_filters, C_out, kernel_size=3, padding=1)
        
    def forward(self, x):
        x = self.in_layer(x)
        skip_connections = [x]

        for i in range(self.depth):
            x = self.pools[i](x)
            x = self.encoders[i](x)
            x = self.postencoders[i](x)
            x = self.attention_forward(x, self.enAttentions[i])
            skip_connections.append(x)

        for i in range(self.depth):
            upsampled = self.upsamples[i](x)
            cropped = self.crop_tensor(upsampled, skip_connections[-(i+2)])
            x = torch.cat([cropped, upsampled], 1)
            x = self.predecoders[i](x)
            x = self.decoders[i](x)
            x = self.postdecoders[i](x)
            x = self.attention_forward(x, self.decAttentions[i])


        x = self.out_layer(x)
        return x

    def crop_tensor(self, target_tensor, tensor):
        target_size = target_tensor.size()[2]  # Assuming height and width are same
        tensor_size = tensor.size()[2]
        delta = tensor_size - target_size
        delta = delta // 2
        return tensor[:, :, delta:tensor_size-delta, delta:tensor_size-delta]
    
    def attention_forward(self, x, fcs):
        b, c, _, _ = x.size()
        y = nn.AdaptiveAvgPool2d(1)(x).view(b, c)
        y = fcs(y).view(b, c, 1, 1)
        return x * y.expand_as(x)
    

class exportedUNet(nn.Module):
    def __init__(self, C_in, C_out, depth, exported_arch):
        super().__init__()

        self.depth = depth
        start_filters = end_filters = 64
        self.in_layer = nn.Conv2d(C_in, start_filters, kernel_size=3, padding=1)

        mid_in = 64
        self.pools = nn.ModuleList()
        self.encoders = nn.ModuleList()
        self.postencoders = nn.ModuleList()
        self.enAttentions = nn.ModuleList()

        for i in range(depth):
            self.pools.append(pools()[exported_arch[f'pool {i}/op_1_0']])
            self.encoders.append(convs(mid_in, mid_in*2)[exported_arch[f'encoder {i}/op_1_0']])
            mid_in *= 2

        
        # decoder layers
        self.upsamples = nn.ModuleList()
        self.predecoders = nn.ModuleList()
        self.decoders = nn.ModuleList()
        self.postdecoders = nn.ModuleList()
        self.decAttentions = nn.ModuleList()
        for i in range(self.depth):
            self.upsamples.append(upsamples(mid_in, mid_in)[exported_arch[f'upsample {i}/op_1_0']])
            mid_in //= 2
            self.decoders.append(convs(mid_in*3, mid_in)[exported_arch[f'decoder {i}/op_1_0']])

        self.out_layer = nn.Conv2d(end_filters, C_out, kernel_size=3, padding=1)
        
    def forward(self, x):
        x = self.in_layer(x)
        skip_connections = [x]

        for i in range(self.depth):
            x = self.pools[i](x)
            x = self.encoders[i](x)
            skip_connections.append(x)

        for i in range(self.depth):
            upsampled = self.upsamples[i](x)
            cropped = self.crop_tensor(upsampled, skip_connections[-(i+2)])
            x = torch.cat([cropped, upsampled], 1)
            x = self.decoders[i](x)
        x = self.out_layer(x)
        return x

    def crop_tensor(self, target_tensor, tensor):
        target_size = target_tensor.size()[2]  # Assuming height and width are same
        tensor_size = tensor.size()[2]
        delta = tensor_size - target_size
        delta = delta // 2
        return tensor[:, :, delta:tensor_size-delta, delta:tensor_size-delta]

