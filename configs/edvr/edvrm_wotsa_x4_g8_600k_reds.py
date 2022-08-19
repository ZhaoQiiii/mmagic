_base_ = '../_base_/models/base_edvr_config.py'

experiment_name = 'edvrm_wotsa_x4_g8_600k_reds'
work_dir = f'./work_dirs/{experiment_name}'

# model settings
model = dict(
    type='EDVR',
    generator=dict(
        type='EDVRNet',
        in_channels=3,
        out_channels=3,
        mid_channels=64,
        num_frames=5,
        deform_groups=8,
        num_blocks_extraction=5,
        num_blocks_reconstruction=10,
        center_frame_idx=2,
        with_tsa=False),
    pixel_loss=dict(type='CharbonnierLoss', loss_weight=1.0, reduction='sum'),
    train_cfg=dict(tsa_iter=5000),
    data_preprocessor=dict(
        type='EditDataPreprocessor',
        mean=[0., 0., 0.],
        std=[255., 255., 255.],
        input_view=(1, -1, 1, 1),
        output_view=(-1, 1, 1),
    ))

# optimizer
optim_wrapper = dict(
    dict(
        type='OptimWrapper',
        optimizer=dict(type='Adam', lr=4e-4, betas=(0.9, 0.999)),
    ))

# learning policy
lr_config = dict(
    policy='CosineRestartLR',
    by_epoch=False,
    periods=[150000, 150000, 150000, 150000],
    restart_weights=[1, 0.5, 0.5, 0.5],
    min_lr=1e-7)