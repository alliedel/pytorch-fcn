import os.path as osp

import instanceseg.utils.configs
import instanceseg.utils.logs
import instanceseg.utils.misc
import instanceseg.utils.scripts
from instanceseg.utils.scripts import setup, configure

here = osp.dirname(osp.abspath(__file__))


def get_single_img_data(dataloader, idx=0):
    img, sem_lbl, inst_lbl = None, None, None
    for i, (img, (sem_lbl, inst_lbl)) in enumerate(dataloader):
        if i != idx:
            continue
    return img, (sem_lbl, inst_lbl)


def main():
    # resume = '/home/adelgior/code/fcn-instance-cityscapes/tests/logs/synthetic/'
    # 'TIME-20180911-162519_VCS-7f69ed0_MODEL-overfit_single_image_CFG-000_SAMPLER-overfit_1_INSTMET-1_ITR-1000'
    # '_LOSS-cross_entropy_N_IMAGES_TRAIN-0_N_IMAGES_VAL-0_SA-0_VAL-10/model_best.pth'
    resume = None
    args, cfg_override_args = instanceseg.utils.scripts.parse_args_without_sys(dataset_name='synthetic', resume=resume)
    # cfg_override_args.loss_type, cfg_override_args.size_average = 'soft_iou', False
    cfg_override_args.loss_type, cfg_override_args.size_average = 'cross_entropy', True
    cfg_override_args.max_iteration = 500
    cfg_override_args.interval_validate = 10
    cfg_override_args.sampler = 'overfit_1'
    cfg_override_args.n_images_train = 1
    cfg_override_args.n_images_val = 1
    cfg_override_args.write_instance_metrics = False
    # cfg_override_args.lr = 1.0e-4
    cfg, out_dir, sampler_cfg = configure(dataset_name=args.dataset,
                                          config_idx=args.config,
                                          sampler_name=args.sampler,
                                          script_py_file=__file__,
                                          cfg_override_args=cfg_override_args,
                                          parent_script_directory=osp.basename(osp.dirname(here)))
    trainer = setup(args.dataset, cfg, out_dir, sampler_cfg, gpu=args.gpu, resume=args.resume,
                    semantic_init=args.semantic_init)

    trainer.train()
    train_loss, train_metrics, _ = trainer.validate_split('train')

    import ipdb;
    ipdb.set_trace()


if __name__ == '__main__':
    main()
