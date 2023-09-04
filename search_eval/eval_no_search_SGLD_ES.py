from nni import trace, report_intermediate_result, report_final_result
from nni.retiarii.evaluator.pytorch import LightningModule
from nni.retiarii.evaluator.pytorch.lightning import DataLoader

import pytorch_lightning as pl
from pytorch_lightning.callbacks import ModelCheckpoint

from skimage.metrics import peak_signal_noise_ratio as compare_psnr

import torch
from torch.optim import Optimizer
from torch.utils.data import Dataset
from torch import tensor, optim

import matplotlib.pyplot as plt

from typing import Any
import numpy as np

from .utils.common_utils import get_noise

torch.backends.cudnn.enabled = True
torch.backends.cudnn.benchmark =True
dtype = torch.cuda.FloatTensor

@trace
class SingleImageDataset(Dataset):
    """
    Dataset that always returns the same image
    """
    def __init__(self, image, num_iter):
        self.image = image
        self.num_iter = num_iter

    def __len__(self):
        return self.num_iter

    def __getitem__(self, index):
        # Always return the same image (and maybe a noise tensor or other information if necessary??)
        return self.image

@trace
class Eval_SGLD_ES(LightningModule):
    def __init__(self, 
                 phantom=None, 
                 phantom_noisy=None,
                 lr=0.01,
                 reg_noise_std_val=1./30., 
                 MCMC_iter=50,
                 model=None, 
                 show_every=200,
                 buffer_size=100,
                 patience=1000,
                 HPO=False
                ):
        super().__init__()
        torch.autograd.set_detect_anomaly(True)
        self.automatic_optimization = True
        self.HPO = HPO
        
        # network features
        if model is None:
            model = torch.hub.load('mateuszbuda/brain-segmentation-pytorch', 'unet', in_channels=1, out_channels=1, init_features=64, pretrained=False)
        self.model_cls = model
        self.model = model
        self.input_depth = 1

        # loss
        self.total_loss = 10
        self.criteria = torch.nn.MSELoss().type(dtype)

        # "Early Stopper" Trigger
        self.reg_noise_std = tensor(reg_noise_std_val)
        self.learning_rate = lr
        self.roll_back = True # to prevent numerical issues
        self.weight_decay = 5e-8
        self.show_every =  show_every

        # SGLD
        self.sgld_mean_each = 0
        self.sgld_psnr_mean_list = []
        self.MCMC_iter = MCMC_iter
        self.sgld_mean = 0
        self.last_net = None
        self.psnr_noisy_last = 0
        self.param_noise_sigma = 2
        
        # burnin-end criteria
        self.img_collection = []
        self.variance_history = []
        self.patience = patience
        self.wait_count = 0
        self.best_score = float('inf')
        self.best_epoch = 0
        self.img_collection = []
        self.burnin_over = False
        self.buffer_size = buffer_size
        self.cur_var = None

        # image and noise
        # move to float 32 instead of float 64

        self.phantom = np.float32(phantom)
        self.img_np = np.float32(phantom)
        self.img_noisy_np = np.float32(phantom_noisy)

        self.img_noisy_torch = torch.tensor(self.img_noisy_np, dtype=torch.float32).unsqueeze(0)
        self.net_input = get_noise(self.input_depth, 'noise', (self.img_np.shape[-2:][1], self.img_np.shape[-2:][0])).type(self.dtype).detach()

    def configure_optimizers(self) -> Optimizer:
        """
        We are doing a manual implementation of the SGLD optimizer
        There is a SGLD optimizer that can be found here:
            - https://pysgmcmc.readthedocs.io/en/pytorch/_modules/pysgmcmc/optimizers/sgld.html
            - Implementing this would greatly simplify the training step
                - But could it work?? :`( I couldn't figure it out
        """
        return torch.optim.Adam(self.model.parameters(), lr=self.learning_rate, weight_decay=self.weight_decay)
    
    def on_train_start(self):
        """
        Move all tensors to the GPU to begin training
        """
        self.model.to(self.device)
        self.net_input = self.net_input.to(self.device)
        self.img_noisy_torch = self.img_noisy_torch.to(self.device)
        self.reg_noise_std = self.reg_noise_std.to(self.device)

        self.net_input_saved = self.net_input.clone().to(self.device)
        self.noise = self.net_input.clone().to(self.device)
        self.i = 0
        self.sample_count = 0
        self.burnin_iter = 0
        self.report_every = self.show_every/5
          
    def forward(self, net_input_saved):
        torch.autograd.set_detect_anomaly(True)
        if self.reg_noise_std > 0:
            net_input = net_input_saved + (self.noise.normal_() * self.reg_noise_std)
            return self.model(net_input)
        else:
            return self.model(net_input_saved)

    def update_burnin(self,out_np):
        """
        Componenet of closure function
        check if we should end the burnin phase
        """
        # update img collection
        v_img_np = out_np.reshape(-1)
        self.update_img_collection(v_img_np)
        img_collection = self.get_img_collection()

        if len(img_collection) >= self.buffer_size:
            # update variance and var history
            ave_img = np.mean(img_collection, axis=0)
            variance = [self.MSE(ave_img, tmp) for tmp in img_collection]
            self.cur_var = np.mean(variance)
            self.variance_history.append(self.cur_var)
            self.check_stop(self.cur_var, self.i)
    
    def backtracking(self, psrn_noisy, total_loss):
        """
        Componenet of closure function
        backtracking to prevent oscillation if the PSNR is fluctuating
        """
        if self.roll_back and self.i % self.show_every:
            if psrn_noisy - self.psrn_noisy_last < -5: 
                print('Falling back to previous checkpoint.')
                for new_param, net_param in zip(self.last_net, self.model.parameters()):
                    net_param.detach().copy_(new_param.cuda())
                return total_loss*0
            else:
                self.last_net = [x.detach().cpu() for x in self.model.parameters()]
                self.psrn_noisy_last = psrn_noisy

    def closure(self):
        torch.autograd.set_detect_anomaly(True)
        out = self.forward(self.net_input)

        # compute loss
        self.total_loss = self.criteria(out, self.img_noisy_torch)
        self.latest_loss = self.total_loss.item()
        #total_loss.backward() ### not for NAS
        # total_loss.backward(retain_graph=True) # retain_graph=True is for NAS to work
        out_np = out.detach().cpu().numpy()[0]

        # compute PSNR
        psrn_noisy = compare_psnr(self.img_noisy_np, out.detach().cpu().numpy()[0])
        psrn_gt    = compare_psnr(self.img_np, out_np)

        # early burn in termination criteria
        if not self.burnin_over:
            self.update_burnin(out_np)

        ##########################################
        ### Logging and SGLD mean collection #####
        ##########################################
        
        if self.burnin_over and np.mod(self.i, self.MCMC_iter) == 0:
            self.sgld_mean += out_np
            self.sample_count += 1.

        if self.burnin_over:
            self.burnin_iter+=1
            self.sgld_mean_each += out_np
            self.sgld_mean_tmp = self.sgld_mean_each / self.burnin_iter
            self.sgld_mean_psnr_each = compare_psnr(self.img_np, self.sgld_mean_tmp)

            if self.i % self.report_every == 0:
                # print('Iter: %d; psnr_gt %.2f; psnr_sgld %.2f' % (self.i, psrn_gt, self.sgld_mean_psnr_each))
                if self.HPO:
                    report_intermediate_result({
                        'psnr_gt': round(psrn_gt,5),
                        })
                else:
                    report_intermediate_result({
                        'iteration': self.i,
                        'loss': round(self.latest_loss,5),
                        'psnr_gt': round(psrn_gt,5),
                        'psnr': round(self.sgld_mean_psnr_each,5)
                        })

        elif self.cur_var is not None and not self.burnin_over:
            if self.i % self.report_every == 0:
                # print('Iter: %d; psnr_gt %.2f; loss %.5f; var %.8f' % (self.i, psrn_gt, total_loss, self.cur_var))
                if self.HPO:
                    report_intermediate_result({
                        'psnr_gt': round(psrn_gt,5),
                        })
                else:
                    report_intermediate_result({
                        'iteration': self.i,
                        'loss': round(self.latest_loss,5),
                        'psnr_gt': round(psrn_gt,5),
                        'var': round(self.cur_var,5)
                        })

        else:
            if self.i % self.report_every == 0:
                # print('Iter: %d; psnr_gt %.2f; loss %.5f' % (self.i, psrn_gt, total_loss))
                if self.HPO:
                    report_intermediate_result({
                        'psnr_gt': round(psrn_gt,5),
                        })
                else:
                    report_intermediate_result({
                        'iteration': self.i,
                        'loss': round(self.latest_loss,5),
                        'psnr_gt': round(psrn_gt,5)
                        })

        self.i += 1
        return self.total_loss

    def add_noise(self, net):
        """
        Add noise to the network parameters
        This is the critical part of SGLD
        """
        for n in [x for x in net.parameters() if len(x.size()) == 4]:
            noise = torch.randn(n.size())*self.param_noise_sigma*self.learning_rate
            #noise = noise.type(self.dtype)
            noise = noise.type(self.dtype).to(self.device)
            n.data = n.data + noise

    def training_step(self, batch: Any, batch_idx: int) -> Any:
        """
        Oh the places you'll go
        ---> Straight to error city calling this add_noise in the training step
        ---> Consider using the on_train_batch_end hook? (each batch is only one iteration)
        """
        # optimizer = self.optimizers()
        # optimizer.zero_grad()
        loss = self.closure()
        # optimizer.step()
        return {"loss": loss}

    def on_train_batch_end(self, outputs, batch, batch_idx, *args, **kwargs):
        """
        Add noise for SGLD
        """
        optimizer = self.optimizers()
        if isinstance(optimizer, torch.optim.Adam):
            self.add_noise(self.model)

        if self.i % self.show_every == 0:
            self.plot_progress()

    def on_train_end(self, **kwargs: Any):
        """
        Report final metrics and display the results
        """
        # final log
        report_final_result({'loss': self.latest_loss})

        # # plot images to see results
        self.plot_progress()
        final_sgld_mean = self.sgld_mean / self.sample_count
        final_sgld_mean_psnr = compare_psnr(self.img_np, final_sgld_mean)
        print(f"Final SGLD mean PSNR: {final_sgld_mean_psnr}")
        report_final_result({'psnr_gt': final_sgld_mean_psnr})

    def common_dataloader(self):
        # dataset = SingleImageDataset(self.phantom, self.num_iter)
        dataset = SingleImageDataset(self.phantom, 1)
        return DataLoader(dataset, batch_size=1)

    def train_dataloader(self):
        return self.common_dataloader()
    
    def optimizer_zero_grad(self, epoch, batch_idx, optimizer, opt_idx):
        # Not sure if this is the default logic in the nni.retiarii.evaluator.pytorch.LightningModule
        # needed to modify so it can accept the opt_idx argument
        optimizer.zero_grad()
    
    def configure_gradient_clipping(self, optimizer, opt_idx, gradient_clip_val, gradient_clip_algorithm):
        # Not sure if this is the default logic in the nni.retiarii.evaluator.pytorch.LightningModule
        # needed to modify so it can accept the opt_idx argument
        # now need to define the clipping logic
        self.clip_gradients(
            optimizer,
            gradient_clip_val=gradient_clip_val,
            gradient_clip_algorithm=gradient_clip_algorithm
        )

    def check_stop(self, current, cur_epoch):
        """
        using an early stopper technique to determine when to end the burn in phase for SGLD
        https://arxiv.org/pdf/2112.06074.pdf
        https://github.com/sun-umn/Early_Stopping_for_DIP/blob/main/ES_WMV.ipynb
        """
        if current < self.best_score:
            self.best_score = current
            self.best_epoch = cur_epoch
            self.wait_count = 0
            self.burnin_over = False
        else:
            self.wait_count += 1
            self.burnin_over = self.wait_count >= self.patience
        if self.burnin_over:
            print(f'\n\nBurn-in completed at iter {self.i}; \nStarting SGLD Mean sampling;\n\n')
            self.show_every = self.MCMC_iter

    def update_img_collection(self, cur_img):
        self.img_collection.append(cur_img)
        if len(self.img_collection) > self.buffer_size:
            self.img_collection.pop(0)

    def get_img_collection(self):
        return self.img_collection

    def MSE(self, x1, x2):
        return ((x1 - x2) ** 2).sum() / x1.size
        
    def plot_progress(self):
        if self.sample_count == 0:
            denoised_img = self.forward(self.net_input).detach().cpu().squeeze().numpy()
            label = "Denoised Image"
        else:
            denoised_img = self.sgld_mean_each / self.burnin_iter
            # denoised_img = self.sgld_mean / self.sample_count if self.sample_count > 0 else self.sgld_mean
            denoised_img = np.squeeze(denoised_img)
            label = "SGLD Mean"

        _, self.ax = plt.subplots(1, 3, figsize=(10, 5))
        
        #self.ax[0].clear()
        #self.ax[1].clear()
        #self.ax[2].clear()

        self.ax[0].imshow(self.img_np.squeeze(), cmap='gray')
        self.ax[0].set_title("Original Image")
        self.ax[0].axis('off')

        self.ax[1].imshow(denoised_img, cmap='gray')
        self.ax[1].set_title(label)
        self.ax[1].axis('off')

        self.ax[2].imshow(self.img_noisy_torch.detach().cpu().squeeze().numpy(), cmap='gray')
        self.ax[2].set_title("Noisy Image")
        self.ax[2].axis('off')

        #clear_output(wait=True)

        plt.tight_layout()
        plt.show()
