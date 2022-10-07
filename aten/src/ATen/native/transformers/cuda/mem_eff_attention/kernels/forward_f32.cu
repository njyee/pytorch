// This file is auto-generated. See "generate_kernels.sh"
#include <ATen/native/transformers/cuda/mem_eff_attention/kernel_forward.h>
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM50(float, false, 32, 128, true);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM50(float, false, 32, 128, false);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM50(float, false, 64, 64, true);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM70(float, false, 32, 128, true);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM70(float, false, 32, 128, false);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM70(float, false, 64, 64, true);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM75(float, false, 32, 128, true);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM75(float, false, 32, 128, false);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM75(float, false, 64, 64, true);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM80(float, false, 32, 128, true);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM80(float, false, 32, 128, false);
INSTANTIATE_ATTENTION_KERNEL_FORWARD_SM80(float, false, 64, 64, true);
