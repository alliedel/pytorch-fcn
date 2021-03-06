class PARAM_CLASSIFICATIONS(object):
    debug = {'debug_dataloader_only', 'n_debug_images'}
    optim = {'optim', 'max_iteration', 'lr', 'momentum', 'weight_decay', 'reset_optim'}
    export = {'interval_validate', 'export_activations', 'activation_layers_to_export', 'write_instance_metrics',
              'n_model_checkpoints', 'skip_validation', 'validation_gpu'}
    loss = {'matching', 'size_average', 'loss_type', 'lr_scheduler'}
    data = {'semantic_only_labels', 'set_extras_to_void', 'semantic_subset', 'ordering', 'sampler', 'dataset',
            'dataset_instance_cap', 'resize', 'resize_size', 'dataset_path', 'train_batch_size',
            'val_batch_size', 'test_batch_size', 'instance_id_for_excluded_instances', 'blob_size',
            'debug_dataloader_only', 'n_debug_images'}
    problem_config = {'n_instances_per_class', 'single_instance', 'map_to_semantic', 'augment_semantic'}
    model = {'backbone', 'initialize_from_semantic', 'bottleneck_channel_capacity', 'score_multiplier', 'freeze_vgg',
             'map_to_semantic', 'augment_semantic', 'use_conv8', 'use_attn_layer', 'clip'}
    misc = {'interactive_dataloader'},
    test = {'test_batch_size'}

# NOTE(allie): Do not directly access this dictionary unless you want to change it for *every* module that imports
# this one.  Ran into issues not copying this dictionary when I started changing it, and it changes all the config
# dictionaries.


_default_train_config = dict(

    # losses
    matching=True,
    size_average=True,
    loss_type='cross_entropy',  # 'cross_entropy' ('xent'), 'softiou'

    # optim
    optim='sgd',
    reset_optim=True,  # with resume
    max_iteration=100000,
    lr=1.0e-12,
    momentum=0.99,
    weight_decay=0.0005,
    clip=1e20,
    lr_scheduler=None,  #'plateau',

    # exportno
    interval_validate=100,
    skip_validation=False,
    validation_gpu=None,
    export_activations=False,
    activation_layers_to_export=('conv1.conv0',
                                 'conv3.pool', 'conv4.pool', 'conv5.pool', 'drop6', 'fc7', 'drop7', 'upscore8'),
                                # 'conv1x1_instance_to_semantic'
    write_instance_metrics=False,
    n_model_checkpoints=None, # None: every validation iteration; max 100

    # debug
    debug_dataloader_only=False,
    n_debug_images=None,

    # data
    dataset=None,
    dataset_path=None,
    dataset_instance_cap='match_model',  #
    semantic_subset=None,
    ordering=None,  # 'lr'
    sampler=None,
    resize=False,
    resize_size=None,
    train_batch_size=1,
    val_batch_size=1,
    test_batch_size=1,
    instance_id_for_excluded_instances=None,  # -1 for void
    # semantic_only_labels=False,
    # set_extras_to_void=True,

    # problem_config
    n_instances_per_class=None,
    single_instance=False,  # map_to_single_instance_problem

    # model
    backbone='resnet50',
    initialize_from_semantic=False,
    bottleneck_channel_capacity=None,
    score_multiplier=None,
    freeze_vgg=False,
    map_to_semantic=False,
    augment_semantic=False,
    use_conv8=False,
    use_attn_layer=False,
)

_default_test_config = dict(
    # saved model
    logdir=None,
    model_file=None,
    train_config=None,

    # debug
    debug_dataloader_only=False,
    n_debug_images=None,

    # data
    dataset=None,
    dataset_path=None,
    dataset_instance_cap='match_model',  #
    semantic_subset=None,
    ordering=None,  # 'lr'
    sampler=None,
    resize=False,
    resize_size=None,
    test_batch_size=1,
)


def get_default_test_config():
    default_test_config = _default_test_config.copy()
    return default_test_config


def get_default_train_config():
    return _default_train_config.copy()


def assert_all_cfg_keys_classified():
    keys = list(_default_train_config.keys())
    param_groups = [x for x in list(PARAM_CLASSIFICATIONS.__dict__.keys()) if x[0] != '_']
    unclassified_keys = []
    for k in keys:
        if not any([k in getattr(PARAM_CLASSIFICATIONS, param_group)
                    for param_group in param_groups]):
            unclassified_keys.append(k)
    if len(unclassified_keys) > 0:
        raise Exception('The following parameters have not yet been classified in PARAM_CLASSIFICATIONS: {}'.format(
            unclassified_keys))


assert_all_cfg_keys_classified()
