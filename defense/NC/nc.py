




# MIT License
#
# Copyright (C) The Adversarial Robustness Toolbox (ART) Authors 2018
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""
This module implements methods performing poisoning detection based on activations clustering.
| Paper link: https://arxiv.org/abs/1811.03728
| Please keep in mind the limitations of defences. For more information on the limitations of this
    defence, see https://arxiv.org/abs/1905.13409 . For details on how to evaluate classifier security
    in general, see https://arxiv.org/abs/1902.06705
"""
import logging
import random
import time

from calendar import c

import torch
import logging
import argparse
import sys
import os
from torch import Tensor, nn

sys.path.append('../')
sys.path.append(os.getcwd())
import pickle
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import numpy as np
import torchvision
from utils.aggregate_block.model_trainer_generate import generate_cls_model
from utils.aggregate_block.dataset_and_transform_generate import get_transform
from utils.bd_dataset import prepro_cls_DatasetBD
from utils.nCHW_nHWC import *
from utils.save_load_attack import load_attack_result
sys.path.append(os.getcwd())
import yaml
from pprint import pprint, pformat
# def create_dir(path_dir):
#     list_subdir = path_dir.strip(".").split("/")
#     list_subdir.remove("")
#     base_dir = "./"
#     for subdir in list_subdir:
#         base_dir = os.path.join(base_dir, subdir)
#         try:
#             os.mkdir(base_dir)
#         except:
#             pass

class Normalize:

    def __init__(self, opt, expected_values, variance):
        self.n_channels = opt.input_channel
        self.expected_values = expected_values
        self.variance = variance
        assert self.n_channels == len(self.expected_values)

    def __call__(self, x):
        x_clone = x.clone()
        for channel in range(self.n_channels):
            x_clone[:, channel] = (x[:, channel] - self.expected_values[channel]) / self.variance[channel]
        return x_clone

class Denormalize:

    def __init__(self, opt, expected_values, variance):
        self.n_channels = opt.input_channel
        self.expected_values = expected_values
        self.variance = variance
        assert self.n_channels == len(self.expected_values)

    def __call__(self, x):
        x_clone = x.clone()
        for channel in range(self.n_channels):
            x_clone[:, channel] = x[:, channel] * self.variance[channel] + self.expected_values[channel]
        return x_clone

class RegressionModel(nn.Module):
    def __init__(self, opt, init_mask, init_pattern,result):
        self._EPSILON = opt.EPSILON
        super(RegressionModel, self).__init__()
        self.mask_tanh = nn.Parameter(torch.tensor(init_mask))
        self.pattern_tanh = nn.Parameter(torch.tensor(init_pattern))
        self.result = result
        self.classifier = self._get_classifier(opt)
        self.normalizer = self._get_normalize(opt)
        self.denormalizer = self._get_denormalize(opt)

        

    def forward(self, x):
        mask = self.get_raw_mask()
        pattern = self.get_raw_pattern()
        if self.normalizer:
            pattern = self.normalizer(self.get_raw_pattern())
        x = (1 - mask) * x + mask * pattern
        return self.classifier(x)

    def get_raw_mask(self):
        mask = nn.Tanh()(self.mask_tanh)
        return mask / (2 + self._EPSILON) + 0.5

    def get_raw_pattern(self):
        pattern = nn.Tanh()(self.pattern_tanh)
        return pattern / (2 + self._EPSILON) + 0.5

    def _get_classifier(self, opt):
        # if opt.dataset == "mnist":
        #     classifier = NetC_MNIST()
        # elif opt.dataset == "cifar10":
        #     classifier = PreActResNet18()
        # elif opt.dataset == "gtsrb":
        #     classifier = PreActResNet18(num_classes=43)
        # elif opt.dataset == "celeba":
        #     classifier = ResNet18()
        # else:
        #     raise Exception("Invalid Dataset")
        # if opt.classifier == 'preactresnet18':
        #     classifier = PreActResNet18()
        #     if opt.dataset == "gtsrb":
        #         classifier = PreActResNet18(num_classes=43)
        #     if opt.dataset == "cifar100":
        #         classifier = PreActResNet18(num_classes=100)
        # else:
        #     classifier = CIFAR10Module(opt).model
        # Load pretrained classifie
        # ckpt_path = os.path.join(
        #     opt.checkpoints, opt.dataset, "{}_{}_morph.pth.tar".format(opt.dataset, opt.attack_mode)
        # )

        # state_dict = torch.load(ckpt_path)
        # classifier.load_state_dict(state_dict["netC"])
        classifier = generate_cls_model(args.model,args.num_classes)
        classifier.load_state_dict(self.result['model'])
        classifier.to(args.device)
        # checkpoint = torch.load(opt.checkpoint_load)
        # classifier.load_state_dict(checkpoint['model'])
        for param in classifier.parameters():
            param.requires_grad = False
        classifier.eval()
        return classifier.to(opt.device)

    def _get_denormalize(self, opt):
        if opt.dataset == "cifar10" or opt.dataset == "cifar100":
            denormalizer = Denormalize(opt, [0.4914, 0.4822, 0.4465], [0.247, 0.243, 0.261])
        elif opt.dataset == "mnist":
            denormalizer = Denormalize(opt, [0.5], [0.5])
        elif opt.dataset == "gtsrb" or opt.dataset == "celeba":
            denormalizer = None
        else:
            raise Exception("Invalid dataset")
        return denormalizer

    def _get_normalize(self, opt):
        if opt.dataset == "cifar10" or opt.dataset == "cifar100":
            normalizer = Normalize(opt, [0.4914, 0.4822, 0.4465], [0.247, 0.243, 0.261])
        elif opt.dataset == "mnist":
            normalizer = Normalize(opt, [0.5], [0.5])
        elif opt.dataset == "gtsrb" or opt.dataset == "celeba":
            normalizer = None
        else:
            raise Exception("Invalid dataset")
        return normalizer


class Recorder:
    def __init__(self, opt):
        super().__init__()

        # Best optimization results
        self.mask_best = None
        self.pattern_best = None
        self.reg_best = float("inf")

        # Logs and counters for adjusting balance cost
        self.logs = []
        self.cost_set_counter = 0
        self.cost_up_counter = 0
        self.cost_down_counter = 0
        self.cost_up_flag = False
        self.cost_down_flag = False

        # Counter for early stop
        self.early_stop_counter = 0
        self.early_stop_reg_best = self.reg_best

        # Cost
        self.cost = opt.init_cost
        self.cost_multiplier_up = opt.cost_multiplier
        self.cost_multiplier_down = opt.cost_multiplier ** 1.5

    def reset_state(self, opt):
        self.cost = opt.init_cost
        self.cost_up_counter = 0
        self.cost_down_counter = 0
        self.cost_up_flag = False
        self.cost_down_flag = False
        print("Initialize cost to {:f}".format(self.cost))

    def save_result_to_dir(self, opt):
        # result_dir = os.path.join(opt.result, opt.dataset)
        # if not os.path.exists(result_dir):
        #     os.makedirs(result_dir)
        # # result_dir = os.path.join(result_dir, opt.attack_mode)
        # result_dir = os.path.join(result_dir, opt.trigger_type)
        # if not os.path.exists(result_dir):
        #     os.makedirs(result_dir)
        # result_dir = os.path.join(result_dir, str(opt.target_label))
        # if not os.path.exists(result_dir):
        #     os.makedirs(result_dir)

        result_dir = (os.getcwd() + f'{opt.save_path}/nc/')
        if not os.path.exists(result_dir):
            os.makedirs(result_dir)
        # result_dir = os.path.join(result_dir, opt.attack_mode)
        # result_dir = os.path.join(os.getcwd(),opt.save_path,  opt.trigger_type)
        # if not os.path.exists(result_dir):
        #     os.makedirs(result_dir)
        # result_dir = os.path.join(os.getcwd(),opt.save_path,  str(opt.target_label))
        # if not os.path.exists(result_dir):
        #     os.makedirs(result_dir)

        pattern_best = self.pattern_best
        mask_best = self.mask_best
        trigger = pattern_best * mask_best

        path_mask = os.path.join(result_dir, "mask.png")
        path_pattern = os.path.join(result_dir, "pattern.png")
        path_trigger = os.path.join(result_dir, "trigger.png")

        torchvision.utils.save_image(mask_best, path_mask, normalize=True)
        torchvision.utils.save_image(pattern_best, path_pattern, normalize=True)
        torchvision.utils.save_image(trigger, path_trigger, normalize=True)


def train(opt, result, init_mask, init_pattern):

    tran = get_transform(opt.dataset, *([opt.input_height,opt.input_width]) , train = True)
    x = torch.tensor(nCHW_to_nHWC(result['bd_train']['x'].numpy()))
    y = result['bd_train']['y']
    data_bd_train = torch.utils.data.TensorDataset(x,y)
    data_bd_trainset = prepro_cls_DatasetBD(
        full_dataset_without_transform=data_bd_train,
        poison_idx=np.zeros(len(data_bd_train)),  # one-hot to determine which image may take bd_transform
        bd_image_pre_transform=None,
        bd_label_pre_transform=None,
        ori_image_transform_in_loading=tran,
        ori_label_transform_in_loading=None,
        add_details_in_preprocess=False,
    )
    trainloader = torch.utils.data.DataLoader(data_bd_trainset, batch_size=opt.batch_size, num_workers=opt.num_workers,drop_last=False, shuffle=True,pin_memory=True)
    # test_dataloader = get_dataloader(opt, train=False)
    # trainloader = get_dataloader(opt, True)

    # Build regression model
    regression_model = RegressionModel(opt, init_mask, init_pattern, result).to(opt.device)

    # Set optimizer
    optimizerR = torch.optim.Adam(regression_model.parameters(), lr=opt.lr, betas=(0.5, 0.9))

    # Set recorder (for recording best result)
    recorder = Recorder(opt)

    for epoch in range(opt.nc_epoch):
        # early_stop = train_step(regression_model, optimizerR, test_dataloader, recorder, epoch, opt)
        early_stop = train_step(regression_model, optimizerR, trainloader, recorder, epoch, opt)
        if early_stop:
            break

    # Save result to dir
    recorder.save_result_to_dir(opt)

    return recorder, opt


def train_step(regression_model, optimizerR, dataloader, recorder, epoch, opt):
    # print("Epoch {} - Label: {} | {} - {}:".format(epoch, opt.target_label, opt.dataset, opt.attack_mode))
    # Set losses
    cross_entropy = nn.CrossEntropyLoss()
    total_pred = 0
    true_pred = 0

    # Record loss for all mini-batches
    loss_ce_list = []
    loss_reg_list = []
    loss_list = []
    loss_acc_list = []

    # Set inner early stop flag
    inner_early_stop_flag = False
    for batch_idx, (inputs, labels) in enumerate(dataloader):
        # Forwarding and update model
        optimizerR.zero_grad()

        inputs = inputs.to(opt.device)
        sample_num = inputs.shape[0]
        total_pred += sample_num
        target_labels = torch.ones((sample_num), dtype=torch.int64).to(opt.device) * opt.target_label
        predictions = regression_model(inputs)

        loss_ce = cross_entropy(predictions, target_labels)
        loss_reg = torch.norm(regression_model.get_raw_mask(), opt.use_norm)
        total_loss = loss_ce + recorder.cost * loss_reg
        total_loss.backward()
        optimizerR.step()

        # Record minibatch information to list
        minibatch_accuracy = torch.sum(torch.argmax(predictions, dim=1) == target_labels).detach() * 100.0 / sample_num
        loss_ce_list.append(loss_ce.detach())
        loss_reg_list.append(loss_reg.detach())
        loss_list.append(total_loss.detach())
        loss_acc_list.append(minibatch_accuracy)

        true_pred += torch.sum(torch.argmax(predictions, dim=1) == target_labels).detach()
        # progress_bar(batch_idx, len(dataloader))

    loss_ce_list = torch.stack(loss_ce_list)
    loss_reg_list = torch.stack(loss_reg_list)
    loss_list = torch.stack(loss_list)
    loss_acc_list = torch.stack(loss_acc_list)

    avg_loss_ce = torch.mean(loss_ce_list)
    avg_loss_reg = torch.mean(loss_reg_list)
    avg_loss = torch.mean(loss_list)
    avg_loss_acc = torch.mean(loss_acc_list)

    # Check to save best mask or not
    if avg_loss_acc >= opt.atk_succ_threshold and avg_loss_reg < recorder.reg_best:
        recorder.mask_best = regression_model.get_raw_mask().detach()
        recorder.pattern_best = regression_model.get_raw_pattern().detach()
        recorder.reg_best = avg_loss_reg
        recorder.save_result_to_dir(opt)
        # print(" Updated !!!")

    # Show information
    # print(
    #     "  Result: Accuracy: {:.3f} | Cross Entropy Loss: {:.6f} | Reg Loss: {:.6f} | Reg best: {:.6f}".format(
    #         true_pred * 100.0 / total_pred, avg_loss_ce, avg_loss_reg, recorder.reg_best
    #     )
    # )

    # Check early stop
    if opt.early_stop:
        if recorder.reg_best < float("inf"):
            if recorder.reg_best >= opt.early_stop_threshold * recorder.early_stop_reg_best:
                recorder.early_stop_counter += 1
            else:
                recorder.early_stop_counter = 0

        recorder.early_stop_reg_best = min(recorder.early_stop_reg_best, recorder.reg_best)

        if (
            recorder.cost_down_flag
            and recorder.cost_up_flag
            and recorder.early_stop_counter >= opt.early_stop_patience
        ):
            print("Early_stop !!!")
            inner_early_stop_flag = True

    if not inner_early_stop_flag:
        # Check cost modification
        if recorder.cost == 0 and avg_loss_acc >= opt.atk_succ_threshold:
            recorder.cost_set_counter += 1
            if recorder.cost_set_counter >= opt.patience:
                recorder.reset_state(opt)
        else:
            recorder.cost_set_counter = 0

        if avg_loss_acc >= opt.atk_succ_threshold:
            recorder.cost_up_counter += 1
            recorder.cost_down_counter = 0
        else:
            recorder.cost_up_counter = 0
            recorder.cost_down_counter += 1

        if recorder.cost_up_counter >= opt.patience:
            recorder.cost_up_counter = 0
            print("Up cost from {} to {}".format(recorder.cost, recorder.cost * recorder.cost_multiplier_up))
            recorder.cost *= recorder.cost_multiplier_up
            recorder.cost_up_flag = True

        elif recorder.cost_down_counter >= opt.patience:
            recorder.cost_down_counter = 0
            print("Down cost from {} to {}".format(recorder.cost, recorder.cost / recorder.cost_multiplier_down))
            recorder.cost /= recorder.cost_multiplier_down
            recorder.cost_down_flag = True

        # Save the final version
        if recorder.mask_best is None:
            recorder.mask_best = regression_model.get_raw_mask().detach()
            recorder.pattern_best = regression_model.get_raw_pattern().detach()

    return inner_early_stop_flag

def outlier_detection(l1_norm_list, idx_mapping, opt):
    print("-" * 30)
    print("Determining whether model is backdoor")
    consistency_constant = 1.4826
    median = torch.median(l1_norm_list)
    mad = consistency_constant * torch.median(torch.abs(l1_norm_list - median))
    min_mad = torch.abs(torch.min(l1_norm_list) - median) / mad

    print("Median: {}, MAD: {}".format(median, mad))
    print("Anomaly index: {}".format(min_mad))

    if min_mad < 2:
        print("Not a backdoor model")
    else:
        print("This is a backdoor model")

    if opt.to_file:
        # result_path = os.path.join(opt.result, opt.saving_prefix, opt.dataset)
        # output_path = os.path.join(
        #     result_path, "{}_{}_output.txt".format(opt.attack_mode, opt.dataset, opt.attack_mode)
        # )
        output_path = opt.output_path
        with open(output_path, "a+") as f:
            f.write(
                str(median.cpu().numpy()) + ", " + str(mad.cpu().numpy()) + ", " + str(min_mad.cpu().numpy()) + "\n"
            )
            l1_norm_list_to_save = [str(value) for value in l1_norm_list.cpu().numpy()]
            f.write(", ".join(l1_norm_list_to_save) + "\n")

    flag_list = []
    for y_label in idx_mapping:
        if l1_norm_list[idx_mapping[y_label]] > median:
            continue
        if torch.abs(l1_norm_list[idx_mapping[y_label]] - median) / mad > 2:
            flag_list.append((y_label, l1_norm_list[idx_mapping[y_label]]))

    if len(flag_list) > 0:
        flag_list = sorted(flag_list, key=lambda x: x[1])

    print(
        "Flagged label list: {}".format(",".join(["{}: {}".format(y_label, l_norm) for y_label, l_norm in flag_list]))
    )
    logging.info(
        "Flagged label list: {}".format(",".join(["{}: {}".format(y_label, l_norm) for y_label, l_norm in flag_list]))
    )

    return flag_list


def get_args():
    parser = argparse.ArgumentParser()
    
    parser.add_argument('--device', type=str, help='cuda, cpu')
    parser.add_argument('--checkpoint_load', type=str)
    parser.add_argument('--checkpoint_save', type=str)
    parser.add_argument('--log', type=str)
    parser.add_argument("--data_root", type=str)

    parser.add_argument('--dataset', type=str, help='mnist, cifar10, gtsrb, celeba, tiny') 
    parser.add_argument("--num_classes", type=int)
    parser.add_argument("--input_height", type=int)
    parser.add_argument("--input_width", type=int)
    parser.add_argument("--input_channel", type=int)

    parser.add_argument('--epochs', type=int)
    parser.add_argument('--batch_size', type=int)
    parser.add_argument("--num_workers", type=float)
    parser.add_argument('--lr', type=float)

    parser.add_argument('--attack', type=str)
    parser.add_argument('--poison_rate', type=float)
    parser.add_argument('--target_type', type=str, help='all2one, all2all, cleanLabel') 
    parser.add_argument('--target_label', type=int)
    parser.add_argument('--trigger_type', type=str, help='squareTrigger, gridTrigger, fourCornerTrigger, randomPixelTrigger, signalTrigger, trojanTrigger')

    ####添加额外
    parser.add_argument('--model', type=str, help='resnet18')
    parser.add_argument('--result_file', type=str, help='the location of result')

    #####nc
    parser.add_argument("--init_cost", type=float, default=1e-3)
    parser.add_argument("--bs", type=int, default=64)
    parser.add_argument("--atk_succ_threshold", type=float, default=98.0)
    parser.add_argument("--early_stop", type=bool, default=True)
    parser.add_argument("--early_stop_threshold", type=float, default=99.0)
    parser.add_argument("--early_stop_patience", type=int, default=25)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--cost_multiplier", type=float, default=2)
    parser.add_argument("--total_label", type=int)
    parser.add_argument("--EPSILON", type=float, default=1e-7)
    parser.add_argument("--to_file", type=bool, default=True)
    parser.add_argument("--n_times_test", type=int, default=10)
    parser.add_argument("--use_norm", type=int, default=1)
    parser.add_argument("--k", type=int)
    parser.add_argument('--ratio', type=float, default=1.0, help='ratio of training data')
    parser.add_argument('--cleaning_ratio', type=float, default=0.1, help='ratio of cleaning data')
    parser.add_argument('--unlearning_ratio', type=float, default=0.2, help='ratio of unlearning data')
    parser.add_argument('--nc_epoch', type=int, default=20, help='the epoch for neural cleanse')


    arg = parser.parse_args()

    print(arg)
    return arg

def nc(args,result,config):
    logFormatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)-8s] [%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d:%H:%M:%S',
    )
    logger = logging.getLogger()
    # logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s] %(message)s")
    if args.log is not None and args.log != '':
        fileHandler = logging.FileHandler(os.getcwd() + args.log + '/' + time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime()) + '.log')
    else:
        fileHandler = logging.FileHandler(os.getcwd() + './log' + '/' + time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime()) + '.log')
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)

    logger.setLevel(logging.INFO)
    logging.info(pformat(args.__dict__))
    result_path = os.getcwd() + f'{args.save_path}/nc/trigger/'
    if not os.path.exists(result_path):
        os.makedirs(result_path)
    args.output_path = result_path + "{}_output_clean.txt".format(args.dataset)
    if args.to_file:
        with open(args.output_path, "w+") as f:
            f.write("Output for cleanse:  - {}".format(args.dataset) + "\n")

    init_mask = np.ones((1, args.input_height, args.input_width)).astype(np.float32)
    init_pattern = np.ones((args.input_channel, args.input_height, args.input_width)).astype(np.float32)

    for test in range(args.n_times_test):
        print("Test {}:".format(test))
        logging.info("Test {}:".format(test))
        if args.to_file:
            with open(args.output_path, "a+") as f:
                f.write("-" * 30 + "\n")
                f.write("Test {}:".format(str(test)) + "\n")

        masks = []
        idx_mapping = {}

        for target_label in range(args.num_classes):
            print("----------------- Analyzing label: {} -----------------".format(target_label))
            logging.info("----------------- Analyzing label: {} -----------------".format(target_label))
            args.target_label = target_label
            recorder, args = train(args, result, init_mask, init_pattern)

            mask = recorder.mask_best
            masks.append(mask)
            idx_mapping[target_label] = len(masks) - 1

        l1_norm_list = torch.stack([torch.norm(m, p=args.use_norm) for m in masks])
        print("{} labels found".format(len(l1_norm_list)))
        print("Norm values: {}".format(l1_norm_list))
        logging.info("{} labels found".format(len(l1_norm_list)))
        logging.info("Norm values: {}".format(l1_norm_list))
        flag_list = outlier_detection(l1_norm_list, idx_mapping, args)

    ###unlearning
    model = generate_cls_model(args.model,args.num_classes)
    model.load_state_dict(result['model'])
    model.to(args.device)
    tran = get_transform(args.dataset, *([args.input_height,args.input_width]) , train = True)
    x = torch.tensor(nCHW_to_nHWC(result['clean_train']['x'].numpy()))
    y = result['clean_train']['y']
    idx = random.sample(range(x.size()[0]), args.cleaning_ratio + args.unlearning_ratio)
    idx_clean = idx[0:int(x.size()[0]*args.cleaning_ratio-1)]
    idx_unlearn = idx[int(x.size()[0]*args.cleaning_ratio):int(x.size()[0]*args.cleaning_ratio+x.size()[0]*args.cleaning_ratio-1)]
    x_clean = x[idx_clean]
    #####单个mask
    alpha = 0.2
    mask = masks[idx_mapping[flag_list[0][0]]]
    x_unlearn = x[idx_unlearn]
    for i in range(len(idx_unlearn)):
        x_unlearn[i] = (1 - alpha) * x_unlearn[i] + alpha * torch.tensor(mask.reshape((1, args.input_height, args.input_width, 1))).to(args.device)
        x_np = x_unlearn[i].cpu().numpy()
        x_np = np.clip(x_np.astype('uint8'), 0, 255)
        x_unlearn[i] = torch.tensor(x_np)
    x_new = torch.cat((x_clean,x_unlearn),dim = 0)
    y_new = y[idx]
    data_clean_train = torch.utils.data.TensorDataset(x_new,y_new)
    data_set_o = prepro_cls_DatasetBD(
        full_dataset_without_transform=data_clean_train,
        poison_idx=np.zeros(len(data_clean_train)),  # one-hot to determine which image may take bd_transform
        bd_image_pre_transform=None,
        bd_label_pre_transform=None,
        ori_image_transform_in_loading=tran,
        ori_label_transform_in_loading=None,
        add_details_in_preprocess=False,
    )
    trainloader = torch.utils.data.DataLoader(data_set_o, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=True,pin_memory=True)
  
    optimizer = torch.optim.SGD(model.parameters(), lr=args.lr, momentum=0.9, weight_decay=5e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=100) 
    criterion = torch.nn.CrossEntropyLoss() 
    
    tran = get_transform(args.dataset, *([args.input_height,args.input_width]) , train = False)
    x = torch.tensor(nCHW_to_nHWC(result['bd_test']['x'].numpy()))
    y = result['bd_test']['y']
    data_bd_test = torch.utils.data.TensorDataset(x,y)
    data_bd_testset = prepro_cls_DatasetBD(
        full_dataset_without_transform=data_bd_test,
        poison_idx=np.zeros(len(data_bd_test)),  # one-hot to determine which image may take bd_transform
        bd_image_pre_transform=None,
        bd_label_pre_transform=None,
        ori_image_transform_in_loading=tran,
        ori_label_transform_in_loading=None,
        add_details_in_preprocess=False,
    )
    data_bd_loader = torch.utils.data.DataLoader(data_bd_testset, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=True,pin_memory=True)

    tran = get_transform(args.dataset, *([args.input_height,args.input_width]) , train = False)
    x = torch.tensor(nCHW_to_nHWC(result['clean_test']['x'].numpy()))
    y = result['clean_test']['y']
    data_clean_test = torch.utils.data.TensorDataset(x,y)
    data_clean_testset = prepro_cls_DatasetBD(
        full_dataset_without_transform=data_clean_test,
        poison_idx=np.zeros(len(data_clean_test)),  # one-hot to determine which image may take bd_transform
        bd_image_pre_transform=None,
        bd_label_pre_transform=None,
        ori_image_transform_in_loading=tran,
        ori_label_transform_in_loading=None,
        add_details_in_preprocess=False,
    )
    data_clean_loader = torch.utils.data.DataLoader(data_clean_testset, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=True,pin_memory=True)

    best_acc = 0
    best_asr = 0
    for j in range(args.epochs):
        for i, (inputs,labels) in enumerate(trainloader):  # type: ignore
            model.to(args.device)
            inputs, labels = inputs.to(args.device), labels.to(args.device)
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        
        with torch.no_grad():
            asr_acc = 0
            for i, (inputs,labels) in enumerate(data_bd_loader):  # type: ignore
                inputs, labels = inputs.to(args.device), labels.to(args.device)
                outputs = model(inputs)
                pre_label = torch.max(outputs,dim=1)[1]
                asr_acc += torch.sum(pre_label == labels)/len(data_bd_test)

            
            clean_acc = 0
            for i, (inputs,labels) in enumerate(data_clean_loader):  # type: ignore
                inputs, labels = inputs.to(args.device), labels.to(args.device)
                outputs = model(inputs)
                pre_label = torch.max(outputs,dim=1)[1]
                clean_acc += torch.sum(pre_label == labels)/len(data_clean_test)
        
        if not (os.path.exists(os.getcwd() + f'{args.save_path}/nc/ckpt_best/')):
            os.makedirs(os.getcwd() + f'{args.save_path}/nc/ckpt_best/')
        if best_acc < clean_acc:
            best_acc = clean_acc
            best_asr = asr_acc
            torch.save(
            {
                'model_name':args.model,
                'model': model.cpu().state_dict(),
                'asr': asr_acc,
                'acc': clean_acc
            },
            f'./{args.save_path}/nc/ckpt_best/defense_result.pt'
            )
        logging.info(f'Epoch{j}: clean_acc:{asr_acc} asr:{clean_acc} best_acc:{best_acc} best_asr{best_asr}')

    result['model'] = model
    return result       

   



if __name__ == '__main__':
    
    args = get_args()
    with open("./defense/NC/config/config.yaml", 'r') as stream: 
        config = yaml.safe_load(stream) 
    config.update({k:v for k,v in args.__dict__.items() if v is not None})
    args.__dict__ = config
    if args.dataset == "mnist":
        args.num_classes = 10
        args.input_height = 28
        args.input_width = 28
        args.input_channel = 1
    elif args.dataset == "cifar10":
        args.num_classes = 10
        args.input_height = 32
        args.input_width = 32
        args.input_channel = 3
    elif args.dataset == "gtsrb":
        args.num_classes = 43
        args.input_height = 32
        args.input_width = 32
        args.input_channel = 3
    elif args.dataset == "celeba":
        args.num_classes = 8
        args.input_height = 64
        args.input_width = 64
        args.input_channel = 3
    elif args.dataset == "tiny":
        args.num_classes = 200
        args.input_height = 64
        args.input_width = 64
        args.input_channel = 3
    else:
        raise Exception("Invalid Dataset")
    
    

    ######为了测试临时写的代码
    save_path = '/record/' + args.result_file
    if args.checkpoint_save is None:
        args.checkpoint_save = save_path + '/record/defence/nc/'
        if not (os.path.exists(os.getcwd() + args.checkpoint_save)):
            os.makedirs(os.getcwd() + args.checkpoint_save) 
    if args.log is None:
        args.log = save_path + '/saved/nc/'
        if not (os.path.exists(os.getcwd() + args.log)):
            os.makedirs(os.getcwd() + args.log) 
    args.save_path = save_path
    result = load_attack_result(os.getcwd() + save_path + '/attack_result.pt')
    
    if args.save_path is not None:
        print("Continue training...")
        result_defense = nc(args,result,config)

        tran = get_transform(args.dataset, *([args.input_height,args.input_width]) , train = False)
        x = torch.tensor(nCHW_to_nHWC(result['bd_test']['x'].numpy()))
        y = result['bd_test']['y']
        data_bd_test = torch.utils.data.TensorDataset(x,y)
        data_bd_testset = prepro_cls_DatasetBD(
            full_dataset_without_transform=data_bd_test,
            poison_idx=np.zeros(len(data_bd_test)),  # one-hot to determine which image may take bd_transform
            bd_image_pre_transform=None,
            bd_label_pre_transform=None,
            ori_image_transform_in_loading=tran,
            ori_label_transform_in_loading=None,
            add_details_in_preprocess=False,
        )
        data_bd_loader = torch.utils.data.DataLoader(data_bd_testset, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=True,pin_memory=True)
    
        asr_acc = 0
        for i, (inputs,labels) in enumerate(data_bd_loader):  # type: ignore
            inputs, labels = inputs.to(args.device), labels.to(args.device)
            outputs = result_defense['model'](inputs)
            pre_label = torch.max(outputs,dim=1)[1]
            asr_acc += torch.sum(pre_label == labels)/len(data_bd_test)

        tran = get_transform(args.dataset, *([args.input_height,args.input_width]) , train = False)
        x = torch.tensor(nCHW_to_nHWC(result['clean_test']['x'].numpy()))
        y = result['clean_test']['y']
        data_clean_test = torch.utils.data.TensorDataset(x,y)
        data_clean_testset = prepro_cls_DatasetBD(
            full_dataset_without_transform=data_clean_test,
            poison_idx=np.zeros(len(data_clean_test)),  # one-hot to determine which image may take bd_transform
            bd_image_pre_transform=None,
            bd_label_pre_transform=None,
            ori_image_transform_in_loading=tran,
            ori_label_transform_in_loading=None,
            add_details_in_preprocess=False,
        )
        data_clean_loader = torch.utils.data.DataLoader(data_clean_testset, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=True,pin_memory=True)
    
        clean_acc = 0
        for i, (inputs,labels) in enumerate(data_clean_loader):  # type: ignore
            inputs, labels = inputs.to(args.device), labels.to(args.device)
            outputs = result_defense['model'](inputs)
            pre_label = torch.max(outputs,dim=1)[1]
            clean_acc += torch.sum(pre_label == labels)/len(data_clean_test)


        if not (os.path.exists(os.getcwd() + f'{save_path}/nc/')):
            os.makedirs(os.getcwd() + f'{save_path}/nc/')
        torch.save(
        {
            'model_name':args.model,
            'model': result_defense['model'].cpu().state_dict(),
            'asr': asr_acc,
            'acc': clean_acc
        },
        f'./{save_path}/nc/defense_result.pt'
        )
    else:
        print("There is no target model")