from tensorboardX import SummaryWriter

import torchfcn


def get_trainer(cfg, cuda, model, optim, dataloaders, problem_config, out_dir):
    writer = SummaryWriter(log_dir=out_dir)
    trainer = torchfcn.Trainer(
        cuda=cuda,
        model=model,
        optimizer=optim,
        train_loader=dataloaders['train'],
        val_loader=dataloaders['val'],
        train_loader_for_val=dataloaders['train_for_val'],
        instance_problem=problem_config,
        out=out_dir,
        max_iter=cfg['max_iteration'],
        interval_validate=cfg.get('interval_validate', len(dataloaders['train'])),
        tensorboard_writer=writer,
        matching_loss=cfg['matching'],
        size_average=cfg['size_average'],
        augment_input_with_semantic_masks=cfg['augment_semantic'],
        export_activations=cfg['export_activations'],
        activation_layers_to_export=cfg['activation_layers_to_export'],
        write_instance_metrics=cfg['write_instance_metrics']
    )
    return trainer
