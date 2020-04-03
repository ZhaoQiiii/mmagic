import re

import torch
from mmcv.utils import build_from_cfg

from .registry import OPTIMIZERS


def build_optimizer(model, optimizer_cfg):
    """Build optimizer from configs.

    Args:
        model (:obj:`nn.Module`): The model with parameters to be optimized.
        optimizer_cfg (dict): The config dict of the optimizer.
            Positional fields are:
                - type: class name of the optimizer.
                - lr: base learning rate.
            Optional fields are:
                - any arguments of the corresponding optimizer type, e.g.,
                  weight_decay, momentum, etc.
                - paramwise_options: a dict with 4 accepted fileds
                  (bias_lr_mult, bias_decay_mult, norm_decay_mult,
                  dwconv_decay_mult).
                  `bias_lr_mult` and `bias_decay_mult` will be multiplied to
                  the lr and weight decay respectively for all bias parameters
                  (except for the normalization layers), and
                  `norm_decay_mult` will be multiplied to the weight decay
                  for all weight and bias parameters of normalization layers.
                  `dwconv_decay_mult` will be multiplied to the weight decay
                  for all weight and bias parameters of depthwise conv layers.

    Returns:
        torch.optim.Optimizer: The initialized optimizer.

    Example:
        >>> import torch
        >>> model = torch.nn.modules.Conv1d(1, 1, 1)
        >>> optimizer_cfg = dict(type='SGD', lr=0.01, momentum=0.9,
        >>>                      weight_decay=0.0001)
        >>> optimizer = build_optimizer(model, optimizer_cfg)
    """
    if hasattr(model, 'module'):
        model = model.module

    optimizer_cfg = optimizer_cfg.copy()
    paramwise_options = optimizer_cfg.pop('paramwise_options', None)
    # if no paramwise option is specified, just use the global setting
    if paramwise_options is None:
        params = model.parameters()
    else:
        if not isinstance(paramwise_options, dict):
            raise TypeError(f'paramwise_options must be a dict, '
                            f'but got {type(paramwise_options)}')
        # get base lr and weight decay
        base_lr = optimizer_cfg['lr']
        base_wd = optimizer_cfg.get('weight_decay', None)
        # weight_decay must be explicitly specified if mult is specified
        if ('bias_decay_mult' in paramwise_options
                or 'norm_decay_mult' in paramwise_options
                or 'dwconv_decay_mult' in paramwise_options):
            if base_wd is None:
                raise ValueError('weight_decay cannot be None since '
                                 'at least one decay_mult is set')
        # get param-wise options
        bias_lr_mult = paramwise_options.get('bias_lr_mult', 1.)
        bias_decay_mult = paramwise_options.get('bias_decay_mult', 1.)
        norm_decay_mult = paramwise_options.get('norm_decay_mult', 1.)
        dwconv_decay_mult = paramwise_options.get('dwconv_decay_mult', 1.)
        named_modules = dict(model.named_modules())
        # set param-wise lr and weight decay
        params = []
        for name, param in model.named_parameters():
            param_group = {'params': [param]}
            if not param.requires_grad:
                # FP16 training needs to copy gradient/weight between master
                # weight copy and model weight, it is convenient to keep all
                # parameters here to align with model.parameters()
                params.append(param_group)
                continue

            # for norm layers, overwrite the weight decay of weight and bias
            # TODO: obtain the norm layer prefixes dynamically
            if re.search(r'(bn|gn)(\d+)?.(weight|bias)', name):
                if base_wd is not None:
                    param_group['weight_decay'] = base_wd * norm_decay_mult
            # for other layers, overwrite both lr and weight decay of bias
            elif name.endswith('.bias'):
                param_group['lr'] = base_lr * bias_lr_mult
                if base_wd is not None:
                    param_group['weight_decay'] = base_wd * bias_decay_mult

            module_name = name.replace('.weight', '').replace('.bias', '')
            if module_name in named_modules and base_wd is not None:
                module = named_modules[module_name]
                # if this Conv2d is depthwise Conv2d
                if isinstance(module, torch.nn.Conv2d) and \
                        module.in_channels == module.groups:
                    param_group['weight_decay'] = base_wd * dwconv_decay_mult
            # otherwise use the global settings

            params.append(param_group)

    optimizer_cfg['params'] = params

    return build_from_cfg(optimizer_cfg, OPTIMIZERS)


def build_optimizers(model, cfgs):
    """Build multiple optimizers from configs.

    If `cfgs` contains several dicts for optimizers, then a dict for each
    constructed optimizers will be returned.
    If `cfgs` only contains one optimizer config, the constructed optimizer
    itself will be returned.

    For example
    1) Multiple optimizer configs:
    ```
    optimizer_cfg = dict(
        model1=dict(type='SGD', lr=lr),
        model2=dict(type='SGD', lr=lr))
    ```
    The return dict:
        dict('model1': torch.optim.Optimizer, 'model2': torch.optim.Optimizer)
    2) Single optimizer config:
    ```
    optimizer_cfg = dict(type='SGD', lr=lr)
    ```
    The return is torch.optim.Optimizer.

    Args:
        model (:obj:`nn.Module`): The model with parameters to be optimized.
        cfgs (dict): The config dict of the optimizer.

    Returns:
        dict[torch.optim.Optimizer] | torch.optim.Optimizer: The initialized
        optimizers.
    """
    optimizers = {}
    if hasattr(model, 'module'):
        model = model.module
    # determine whether 'cfgs' has several dicts for optimizers
    is_dict_of_dict = True
    for key, cfg in cfgs.items():
        if not isinstance(cfg, dict):
            is_dict_of_dict = False
    if is_dict_of_dict:
        for key, cfg in cfgs.items():
            cfg_ = cfg.copy()
            module = getattr(model, key)
            optimizers[key] = build_optimizer(module, cfg_)
        return optimizers
    else:
        return build_optimizer(model, cfgs)
