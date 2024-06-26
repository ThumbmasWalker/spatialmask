'''
-----------------------------------------------------------------------------
Copyright (c) 2023, NVIDIA CORPORATION. All rights reserved.

NVIDIA CORPORATION and its licensors retain all intellectual property
and proprietary rights in and to this software, related documentation
and any modifications thereto. Any use, reproduction, disclosure or
distribution of this software and related documentation without an express
license agreement from NVIDIA CORPORATION is strictly prohibited.
-----------------------------------------------------------------------------
''''''
-----------------------------------------------------------------------------
Copyright (c) 2023, NVIDIA CORPORATION. All rights reserved.

NVIDIA CORPORATION and its licensors retain all intellectual property
and proprietary rights in and to this software, related documentation
and any modifications thereto. Any use, reproduction, disclosure or
distribution of this software and related documentation without an express
license agreement from NVIDIA CORPORATION is strictly prohibited.
-----------------------------------------------------------------------------
'''

from functools import partial
import torch
import torch.nn.functional as torch_F
from collections import defaultdict

from imaginaire.models.base import Model as BaseModel
from projects.nerf.utils import nerf_util, camera, render
from projects.neuralangelo.utils import misc
from projects.neuralangelo.utils.modules import NeuralSDF, NeuralRGB, BackgroundNeRF, SpatialMaskNeuralSDF

class Model(BaseModel):

    def __init__(self, cfg_model, cfg_data):
        super().__init__(cfg_model, cfg_data)
        self.cfg_render = cfg_model.render
        self.white_background = cfg_model.background.white
        self.with_background = cfg_model.background.enabled
        self.with_appear_embed = cfg_model.appear_embed.enabled
        self.anneal_end = cfg_model.object.s_var.anneal_end
        self.outside_val = 1000. * (-1 if cfg_model.object.sdf.mlp.inside_out else 1)
        self.image_size_train = cfg_data.train.image_size
        self.image_size_val = cfg_data.val.image_size
        # Define models.
        self.build_model(cfg_model, cfg_data)
        # Define functions.
        self.ray_generator = partial(nerf_util.ray_generator,
                                     camera_ndc=False,
                                     num_rays=cfg_model.render.rand_rays)
        self.sample_dists_from_pdf = partial(nerf_util.sample_dists_from_pdf,
                                             intvs_fine=cfg_model.render.num_samples.fine)
        self.to_full_val_image = partial(misc.to_full_image, image_size=cfg_data.val.image_size)

    def build_model(self, cfg_model, cfg_data):
        # appearance encoding
        if cfg_model.appear_embed.enabled:
            assert cfg_data.num_images is not None
            self.appear_embed = torch.nn.Embedding(cfg_data.num_images, cfg_model.appear_embed.dim)
            if cfg_model.background.enabled:
                self.appear_embed_outside = torch.nn.Embedding(cfg_data.num_images, cfg_model.appear_embed.dim)
            else:
                self.appear_embed_outside = None
        else:
            self.appear_embed = self.appear_embed_outside = None
        
        self.neural_sdf = SpatialMaskNeuralSDF(cfg_model.object.sdf)
        self.neural_rgb = NeuralRGB(cfg_model.object.rgb, feat_dim=cfg_model.object.sdf.mlp.hidden_dim,
                                    appear_embed=cfg_model.appear_embed)
        if cfg_model.background.enabled:
            self.background_nerf = BackgroundNeRF(cfg_model.background, appear_embed=cfg_model.appear_embed)
        else:
            self.background_nerf = None
        if not cfg_model.object.s_var.scheduled:
            self.s_var = torch.nn.Parameter(torch.tensor(cfg_model.object.s_var.init_val, dtype=torch.float32))

    def set_svar(self):
        self.s_var = torch.tensor(12 + 5/(1-(2.7183**(2.5*self.progress + 0.4))), dtype=torch.float32)

    def forward(self, data):
        # Randomly sample and render the pixels.
        output = self.render_pixels(data["pose"], data["intr"], image_size=self.image_size_train,
                                    stratified=self.cfg_render.stratified, sample_idx=data["idx"],
                                    ray_idx=data["ray_idx"])
        return output

    @torch.no_grad()
    def inference(self, data):
        self.eval()
        # Render the full images.
        output = self.render_image(data["pose"], data["intr"], image_size=self.image_size_val,
                                   stratified=False, sample_idx=data["idx"])  # [B,N,C]
        # Get full rendered RGB and depth images.
        rot = data["pose"][..., :3, :3]  # [B,3,3]
        normal_cam = -output["gradient"] @ rot.transpose(-1, -2)  # [B,HW,3]

        ## FINISH ##
        if self.cfg_render.render_mask:
          mask_maps = output['mask_image']


          lf_mask, idxs = torch.max(mask_maps[:,:,0:4], dim=-1)
          lf_mask2, idxs = torch.max(mask_maps[:,:,4:8], dim=-1)
          mf_mask, idxs = torch.max(mask_maps[:,:,8:14], dim=-1)
          hf_mask, idxs = torch.max(mask_maps[:,:,14:16], dim=-1)

          '''  
          mask1 = mask_maps[:,:,0]
          mask2 = mask_maps[:,:,1]
          mask3 = mask_maps[:,:,2]
          mask4 = mask_maps[:,:,3]
          mask5 = mask_maps[:,:,4]
          mask6 = mask_maps[:,:,5]
          mask7 = mask_maps[:,:,6]
          mask8 = mask_maps[:,:,7]
          mask9 = mask_maps[:,:,8]
          mask10 = mask_maps[:,:,9]
          mask11 = mask_maps[:,:,10]
          mask12 = mask_maps[:,:,11]
          mask13 = mask_maps[:,:,12]
          mask14 = mask_maps[:,:,13]
          mask15 = mask_maps[:,:,14]
          mask16 = mask_maps[:,:,15]
          '''
        #print(mask1.unsqueeze(dim=-1).shape)
        output.update(
            lf_map=self.to_full_val_image(lf_mask.unsqueeze(dim=-1)),
            lf2_map=self.to_full_val_image(lf_mask2.unsqueeze(dim=-1)),
            mf_map=self.to_full_val_image(mf_mask.unsqueeze(dim=-1)),
            hf_map=self.to_full_val_image(hf_mask.unsqueeze(dim=-1)),
           # mask_prob_map=self.to_full_val_image(output["mask_prob"].unsqueeze(dim=-1)),
            #mask1_map=self.to_full_val_image(mask1.unsqueeze(dim=-1)),
            #mask2_map=self.to_full_val_image(mask2.unsqueeze(dim=-1)),
            #mask3_map = self.to_full_val_image(mask3.unsqueeze(dim=-1)),
            #mask4_map = self.to_full_val_image(mask4.unsqueeze(dim=-1)),
            #mask5_map = self.to_full_val_image(mask5.unsqueeze(dim=-1)),
            #mask6_map = self.to_full_val_image(mask6.unsqueeze(dim=-1)),
            #mask7_map = self.to_full_val_image(mask7.unsqueeze(dim=-1)),
            #mask8_map = self.to_full_val_image(mask8.unsqueeze(dim=-1)),
            #mask9_map = self.to_full_val_image(mask9.unsqueeze(dim=-1)),
            #mask10_map = self.to_full_val_image(mask10.unsqueeze(dim=-1)),
            #mask11_map = self.to_full_val_image(mask11.unsqueeze(dim=-1)),
            #mask12_map = self.to_full_val_image(mask12.unsqueeze(dim=-1)),
            #mask13_map = self.to_full_val_image(mask13.unsqueeze(dim=-1)),
            #mask14_map = self.to_full_val_image(mask14.unsqueeze(dim=-1)),
            #mask15_map = self.to_full_val_image(mask15.unsqueeze(dim=-1)),
            #mask16_map = self.to_full_val_image(mask16.unsqueeze(dim=-1)),
            rgb_map=self.to_full_val_image(output["rgb"]),  # [B,3,H,W]
            opacity_map=self.to_full_val_image(output["opacity"]),  # [B,1,H,W]
            depth_map=self.to_full_val_image(output["depth"]),  # [B,1,H,W]
            normal_map=self.to_full_val_image(normal_cam),  # [B,3,H,W]
        )
        return output

    def render_image(self, pose, intr, image_size, stratified=False, sample_idx=None):
        """ Render the rays given the camera intrinsics and poses.
        Args:
            pose (tensor [batch,3,4]): Camera poses ([R,t]).
            intr (tensor [batch,3,3]): Camera intrinsics.
            stratified (bool): Whether to stratify the depth sampling.
            sample_idx (tensor [batch]): Data sample index.
        Returns:
            output: A dictionary containing the outputs.
        """
        output = defaultdict(list)
        for center, ray, ray_idxs in self.ray_generator(pose, intr, image_size, full_image=True):
            ray_unit = torch_F.normalize(ray, dim=-1)  # [B,R,3]
            output_batch = self.render_rays(center, ray_unit, sample_idx=sample_idx, stratified=stratified, ray_idx=ray_idxs, 
                                            pose=pose, intr=intr, image_size=image_size, supersample=self.cfg_render.supersampling)
            if not self.training:
                #print(output_batch['dists'].shape, output_batch['mask'].shape)
                dist = render.composite(output_batch["dists"], output_batch["weights"])  # [B,R,1]
                depth = dist / ray.norm(dim=-1, keepdim=True)
                output_batch.update(depth=depth)

                if self.cfg_render.render_mask:
                  ## TO DO UN-HARDCODE
                  mask = render.composite(output_batch['mask'], output_batch['weights'][:,:,:128,:])
                  #mask, _ = torch.max(output_batch['mask'], dim=-2)
                  output_batch.update(mask_image=mask)
            
                '''
                if self.cfg_render.supersampling:
                 # mask, _ = torch.max(output_batch['mask'], dim=-2)
                  #currently using hf masks, score based?
                  hf_mask, idxs = torch.max(mask[..., 14:16], dim=-1)

                  mask_probability = torch.softmax(hf_mask*10, dim=1)
                  #print(mask_probability.max())
                  output_batch["mask_prob"] = mask_probability
                  ss_idxs = torch.multinomial(mask_probability, self.cfg_render.supersamples, replacement=True).squeeze()
                  # index list of indexes for the ss function to work on image
                  ss_ray_image_idxs = ray_idxs[:, ss_idxs]

                  ss_centers, ss_rays = camera.get_center_and_ray_supersampled(pose, intr, image_size, ss_ray_image_idxs, num_samples=1)
                
             
                  ss_ray_unit = torch_F.normalize(ss_rays, dim=-1)    
                
                  #SPEED UP Can we avoid this by simply indexing?
                  with torch.no_grad():
                    ss_near, ss_far, ss_outside = self.get_dist_bounds(ss_centers, ss_ray_unit)
             
                  ss_app, ss_app_outside = self.get_appearance_embedding(sample_idx, ss_ray_unit.shape[1])

                  ss_output_object = self.render_rays_object(ss_centers, ss_ray_unit, ss_near, ss_far, ss_outside, ss_app, stratified=stratified)
             
                  if self.with_background:
                    ss_output_background = self.render_rays_background(ss_centers, ss_ray_unit, ss_far, ss_app_outside, stratified=stratified)
                    # Concatenate object and background samples.
                    ss_rgbs = torch.cat([ss_output_object["rgbs"], ss_output_background["rgbs"]], dim=2)  # [B,R,No+Nb,3]
                    ss_dists = torch.cat([ss_output_object["dists"], ss_output_background["dists"]], dim=2)  # [B,R,No+Nb,1]
                    ss_alphas = torch.cat([ss_output_object["alphas"], ss_output_background["alphas"]], dim=2)  # [B,R,No+Nb]
                 
                  else:
                    ss_rgbs = output_object_ss["rgbs"]  # [B,R,No,3]
                    ss_dists = output_object_ss["dists"]  # [B,R,No,1]
                    ss_alphas = output_object_ss["alphas"]  # [B,R,No]
           
                  ss_weights = render.alpha_compositing_weights(ss_alphas)  # [B,R,No+Nb,1]
                  # Compute weights and composite samples.
                  ss_rgb = render.composite(ss_rgbs, ss_weights)  # [B,R,3]
             
            
                  uniq_idxs, count = torch.unique(ss_idxs, return_counts=True)
                  #FIX ME: make efficient. Average over super samples
                  for uniq_idx, count in zip(uniq_idxs, count):
                    idxmask = torch.where(ss_idxs.squeeze()==uniq_idx, 1, 0)
                    ss_for_av = torch.index_select(ss_rgb, 1, idxmask.nonzero().squeeze(-1))
                    rgb[:, uniq_idx, :] = (rgb[:, uniq_idx, :] + torch.sum(ss_for_av, dim=1))/(1+count)
                


                  if self.white_background:
                    ss_opacity_all = render.composite(1., ss_weights)  # [B,R,1]
                         
                  opacity = torch.cat([output_batch["opacity"], ss_output_object["opacity"]], dim=1) if output_object["opacity"] != None else None  # [B,R,1]/None
             
                  gradient = torch.cat([output_batch["gradient"], ss_output_object["gradient"]], dim=1) if output_object["gradient"] != None else None  # [B,R,1]/None
            
                  gradients = torch.cat([output_batch["gradients"], ss_output_object["gradients"]], dim=1) if output_object["gradients"] != None else None  # [B,R,1]/None
                  '''    
                  # print(torch.unique(ss_idxs, return_counts=True))

            for key, value in output_batch.items():
                if value is not None:    
                    output[key].append(value.detach())
        # Concat each item (list) in output into one tensor. Concatenate along the ray dimension (1)
       
        for key, value in output.items():
            output[key] = torch.cat(value, dim=1)
        return output

    def render_pixels(self, pose, intr, image_size, stratified=False, sample_idx=None, ray_idx=None):
        center, ray = camera.get_center_and_ray(pose, intr, image_size)  # [B,HW,3]
        center = nerf_util.slice_by_ray_idx(center, ray_idx)  # [B,R,3]
        ray = nerf_util.slice_by_ray_idx(ray, ray_idx)  # [B,R,3]
        ray_unit = torch_F.normalize(ray, dim=-1)  # [B,R,3]
        output = self.render_rays(center, ray_unit, sample_idx=sample_idx, stratified=stratified, 
                                  ray_idx=ray_idx, supersample=self.cfg_render.supersampling,
                                  pose=pose, intr=intr, image_size=image_size)
        return output

    def render_rays(self, center, ray_unit, sample_idx=None, stratified=False, ray_idx=None, supersample=False, pose=None, intr=None, image_size=None):
        with torch.no_grad():
            near, far, outside = self.get_dist_bounds(center, ray_unit)
        app, app_outside = self.get_appearance_embedding(sample_idx, ray_unit.shape[1])
        output_object = self.render_rays_object(center, ray_unit, near, far, outside, app, stratified=stratified)
        if self.with_background:
            output_background = self.render_rays_background(center, ray_unit, far, app_outside, stratified=stratified)
            # Concatenate object and background samples.
            rgbs = torch.cat([output_object["rgbs"], output_background["rgbs"]], dim=2)  # [B,R,No+Nb,3]
            dists = torch.cat([output_object["dists"], output_background["dists"]], dim=2)  # [B,R,No+Nb,1]
            alphas = torch.cat([output_object["alphas"], output_background["alphas"]], dim=2)  # [B,R,No+Nb]
        else:
            rgbs = output_object["rgbs"]  # [B,R,No,3]
            dists = output_object["dists"]  # [B,R,No,1]
            alphas = output_object["alphas"]  # [B,R,No]
        weights = render.alpha_compositing_weights(alphas)  # [B,R,No+Nb,1]
        # Compute weights and composite samples.
        rgb = render.composite(rgbs, weights)  # [B,R,3]
        if self.white_background:
            opacity_all = render.composite(1., weights)  # [B,R,1]
            rgb = rgb + (1 - opacity_all)
        # Collect output.


        if supersample and self.neural_sdf.active_levels >= self.cfg_render.supersample_activate_level:
             #print(output_object['mask'].shape) 
            # mask, _ = torch.max(output_object['mask'], dim=-2)
             
             mask = render.composite(output_object['mask'], weights[:,:,:128,:])
             #currently using max hf masks, score based?
             hf_mask, idxs = torch.max(mask[..., 14:16], dim=-1)
            # print(hf_mask.max())
            
             #mask_probability = torch.softmax(hf_mask, dim=1)
             
             mask_probability = (hf_mask + 1e-6)/(hf_mask.sum(dim=1) + 1e-6) 
             print(mask_probability.mean(), mask_probability.std(), mask_probability.max())

             ss_idxs = torch.multinomial(mask_probability, self.cfg_render.supersamples, replacement=True).squeeze()
             # index list of indexes for the ss function to work on image
             uniq, count = torch.unique(ss_idxs, return_counts=True)
            # print(count.max())

             ss_ray_image_idxs = ray_idx[:, ss_idxs]
            
             ss_centers, ss_rays = camera.get_center_and_ray_supersampled(pose, intr, image_size, ss_ray_image_idxs, num_samples=1)    
             ss_ray_unit = torch_F.normalize(ss_rays, dim=-1)    
                
             #SPEED UP Can we avoid this by simply indexing?
             with torch.no_grad():
                ss_near, ss_far, ss_outside = self.get_dist_bounds(ss_centers, ss_ray_unit)
             
             ss_app, ss_app_outside = self.get_appearance_embedding(sample_idx, ss_ray_unit.shape[1])

             ss_output_object = self.render_rays_object(ss_centers, ss_ray_unit, ss_near, ss_far, ss_outside, ss_app, stratified=stratified)
             
             if self.with_background:
                ss_output_background = self.render_rays_background(ss_centers, ss_ray_unit, ss_far, ss_app_outside, stratified=stratified)
                # Concatenate object and background samples.
                ss_rgbs = torch.cat([ss_output_object["rgbs"], ss_output_background["rgbs"]], dim=2)  # [B,R,No+Nb,3]
                ss_dists = torch.cat([ss_output_object["dists"], ss_output_background["dists"]], dim=2)  # [B,R,No+Nb,1]
                ss_alphas = torch.cat([ss_output_object["alphas"], ss_output_background["alphas"]], dim=2)  # [B,R,No+Nb]
             else:
                ss_rgbs = output_object_ss["rgbs"]  # [B,R,No,3]
                ss_dists = output_object_ss["dists"]  # [B,R,No,1]
                ss_alphas = output_object_ss["alphas"]  # [B,R,No]
           
             ss_weights = render.alpha_compositing_weights(ss_alphas)  # [B,R,No+Nb,1]
             # Compute weights and composite samples.
             ss_rgb = render.composite(ss_rgbs, ss_weights)  # [B,R,3]
             
            
             uniq_idxs, count = torch.unique(ss_idxs, return_counts=True)
             #FIX ME: make efficient. Average over super samples
             for uniq_idx, count in zip(uniq_idxs, count):
                idxmask = torch.where(ss_idxs.squeeze()==uniq_idx, 1, 0)
                ss_for_av = torch.index_select(ss_rgb,1, idxmask.nonzero().squeeze(-1))
               # print(ss_for_av, 'RGB',  rgb[:, uniq_idx, :])
                rgb[:, uniq_idx, :] = (rgb[:, uniq_idx, :] + torch.sum(ss_for_av, dim=1))/(1+count)
                


             if self.white_background:
                ss_opacity_all = render.composite(1., ss_weights)  # [B,R,1]
                         
             opacity = output_object["opacity"] #torch.cat([output_object["opacity"], ss_output_object["opacity"]], dim=1) if output_object["opacity"] != None else None  # [B,R,1]/None
             
             gradient = output_object["gradient"] #torch.cat([output_object["gradient"], ss_output_object["gradient"]], dim=1) if output_object["gradient"] != None else None  # [B,R,1]/None
            
             gradients = output_object["gradients"] #torch.cat([output_object["gradients"], ss_output_object["gradients"]], dim=1) if output_object["gradients"] != None else None  # [B,R,1]/None
             
             hessians  = output_object["hessians"] #torch.cat([outputii"_object["hessians"], ss_output_object["hessians"]], dim=1) if output_object["hessians"] != None else None  # [B,R,1]/None

             output = dict(
                rgb=rgb,  # [B,R,3]
                opacity=opacity,  # [B,R,1]/None
                outside=outside,  # [B,R,1]
                dists=dists,#torch.cat([dists, ss_dists], dim=1),  # [B,R,No+Nb,1]
                weights=weights, #torch.cat([weights, ss_weights], dim=1),  # [B,R,No+Nb,1]
                gradient=gradient,  # [B,R,1]/None
                gradients=gradients,  # [B,R,1]/None
                hessians=hessians,  # [B,R,1]/None
                mask=output_object["mask"]
             )
        else:
             output = dict(
                     rgb=rgb,  # [B,R,3]
                     opacity=output_object["opacity"],  # [B,R,1]/None
                     outside=outside,  # [B,R,1]
                     dists=dists,  # [B,R,No+Nb,1]
                     weights=weights,  # [B,R,No+Nb,1]
                     gradient=output_object["gradient"],  # [B,R,3]/None
                     gradients=output_object["gradients"],  # [B,R,No,3]
                     hessians=output_object["hessians"],  # [B,R,No,3]/None
                     mask=output_object["mask"]
             )


        return output

    def render_rays_object(self, center, ray_unit, near, far, outside, app, stratified=False):
        with torch.no_grad():
            dists = self.sample_dists_all(center, ray_unit, near, far, stratified=stratified)  # [B,R,N,3]
        points = camera.get_3D_points_from_dist(center, ray_unit, dists)  # [B,R,N,3]
        sdfs, feats, mask = self.neural_sdf.forward(points)  # [B,R,N,1],[B,R,N,K]
        #print(sdfs.shape, mask.shape)
        sdfs[outside[..., None].expand_as(sdfs)] = self.outside_val
        # Compute 1st- and 2nd-order gradients.
        rays_unit = ray_unit[..., None, :].expand_as(points).contiguous()  # [B,R,N,3]
        gradients, hessians = self.neural_sdf.compute_gradients(points, training=self.training, sdf=sdfs)
        normals = torch_F.normalize(gradients, dim=-1)  # [B,R,N,3]
        rgbs = self.neural_rgb.forward(points, normals, rays_unit, feats, app=app)  # [B,R,N,3]
        # SDF volume rendering.
        alphas = self.compute_neus_alphas(ray_unit, sdfs, gradients, dists, dist_far=far[..., None],
                                          progress=self.progress)  # [B,R,N]
        if not self.training:
            weights = render.alpha_compositing_weights(alphas)  # [B,R,N,1]
            opacity = render.composite(1., weights)  # [B,R,1]
            gradient = render.composite(gradients, weights)  # [B,R,3]
        else:
            opacity = None
            gradient = None
        # Collect output.
        output = dict(
            rgbs=rgbs,  # [B,R,N,3]
            sdfs=sdfs[..., 0],  # [B,R,N]
            dists=dists,  # [B,R,N,1]
            alphas=alphas,  # [B,R,N]
            opacity=opacity,  # [B,R,3]/None
            gradient=gradient,  # [B,R,3]/None
            gradients=gradients,  # [B,R,N,3]
            hessians=hessians,  # [B,R,N,3]/None]
            mask=mask#.sum(dim=-1)
        )
        return output

    def render_rays_background(self, center, ray_unit, far, app_outside, stratified=False):
        with torch.no_grad():
            dists = self.sample_dists_background(ray_unit, far, stratified=stratified)
        points = camera.get_3D_points_from_dist(center, ray_unit, dists)  # [B,R,N,3]
        rays_unit = ray_unit[..., None, :].expand_as(points)  # [B,R,N,3]
        rgbs, densities = self.background_nerf.forward(points, rays_unit, app_outside)  # [B,R,N,3]
        alphas = render.volume_rendering_alphas_dist(densities, dists)  # [B,R,N]
        # Collect output.
        output = dict(
            rgbs=rgbs,  # [B,R,3]
            dists=dists,  # [B,R,N,1]
            alphas=alphas,  # [B,R,N]
        )
        return output

    @torch.no_grad()
    def get_dist_bounds(self, center, ray_unit):
        dist_near, dist_far = nerf_util.intersect_with_sphere(center, ray_unit, radius=1.)
        dist_near.relu_()  # Distance (and thus depth) should be non-negative.
        outside = dist_near.isnan()
        dist_near[outside], dist_far[outside] = 1, 1.2  # Dummy distances. Density will be set to 0.
        return dist_near, dist_far, outside

    def get_appearance_embedding(self, sample_idx, num_rays):
        if self.with_appear_embed:
            # Object appearance embedding.
            num_samples_all = self.cfg_render.num_samples.coarse + \
                self.cfg_render.num_samples.fine * self.cfg_render.num_sample_hierarchy
            app = self.appear_embed(sample_idx)[:, None, None]  # [B,1,1,C]
            app = app.expand(-1, num_rays, num_samples_all, -1)  # [B,R,N,C]
            # Background appearance embedding.
            if self.with_background:
                app_outside = self.appear_embed_outside(sample_idx)[:, None, None]  # [B,1,1,C]
                app_outside = app_outside.expand(-1, num_rays, self.cfg_render.num_samples.background, -1)  # [B,R,N,C]
            else:
                app_outside = None
        else:
            app = app_outside = None
        return app, app_outside

    @torch.no_grad()
    def sample_dists_all(self, center, ray_unit, near, far, stratified=False):
        dists = nerf_util.sample_dists(ray_unit.shape[:2], dist_range=(near[..., None], far[..., None]),
                                       intvs=self.cfg_render.num_samples.coarse, stratified=stratified)
        if self.cfg_render.num_sample_hierarchy > 0:
            points = camera.get_3D_points_from_dist(center, ray_unit, dists)  # [B,R,N,3]
            sdfs = self.neural_sdf.sdf(points)  # [B,R,N]
        for h in range(self.cfg_render.num_sample_hierarchy):
            dists_fine = self.sample_dists_hierarchical(dists, sdfs, inv_s=(64 * 2 ** h))  # [B,R,Nf,1]
            dists = torch.cat([dists, dists_fine], dim=2)  # [B,R,N+Nf,1]
            dists, sort_idx = dists.sort(dim=2)
            if h != self.cfg_render.num_sample_hierarchy - 1:
                points_fine = camera.get_3D_points_from_dist(center, ray_unit, dists_fine)  # [B,R,Nf,3]
                sdfs_fine = self.neural_sdf.sdf(points_fine)  # [B,R,Nf]
                sdfs = torch.cat([sdfs, sdfs_fine], dim=2)  # [B,R,N+Nf]
                sdfs = sdfs.gather(dim=2, index=sort_idx.expand_as(sdfs))  # [B,R,N+Nf,1]
        return dists

    def sample_dists_hierarchical(self, dists, sdfs, inv_s, robust=True, eps=1e-5):
        sdfs = sdfs[..., 0]  # [B,R,N]
        prev_sdfs, next_sdfs = sdfs[..., :-1], sdfs[..., 1:]  # [B,R,N-1]
        prev_dists, next_dists = dists[..., :-1, 0], dists[..., 1:, 0]  # [B,R,N-1]
        mid_sdfs = (prev_sdfs + next_sdfs) * 0.5  # [B,R,N-1]
        cos_val = (next_sdfs - prev_sdfs) / (next_dists - prev_dists + 1e-5)  # [B,R,N-1]
        if robust:
            prev_cos_val = torch.cat([torch.zeros_like(cos_val)[..., :1], cos_val[..., :-1]], dim=-1)  # [B,R,N-1]
            cos_val = torch.stack([prev_cos_val, cos_val], dim=-1).min(dim=-1).values  # [B,R,N-1]
        dist_intvs = dists[..., 1:, 0] - dists[..., :-1, 0]  # [B,R,N-1]
        est_prev_sdf = mid_sdfs - cos_val * dist_intvs * 0.5  # [B,R,N-1]
        est_next_sdf = mid_sdfs + cos_val * dist_intvs * 0.5  # [B,R,N-1]
        prev_cdf = (est_prev_sdf * inv_s).sigmoid()  # [B,R,N-1]
        next_cdf = (est_next_sdf * inv_s).sigmoid()  # [B,R,N-1]
        alphas = ((prev_cdf - next_cdf) / (prev_cdf + eps)).clip_(0.0, 1.0)  # [B,R,N-1]
        weights = render.alpha_compositing_weights(alphas)  # [B,R,N-1,1]
        dists_fine = self.sample_dists_from_pdf(dists, weights=weights[..., 0])  # [B,R,Nf,1]
        return dists_fine

    def sample_dists_background(self, ray_unit, far, stratified=False, eps=1e-5):
        inv_dists = nerf_util.sample_dists(ray_unit.shape[:2], dist_range=(1, 0),
                                           intvs=self.cfg_render.num_samples.background, stratified=stratified)
        dists = far[..., None] / (inv_dists + eps)  # [B,R,N,1]
        return dists

    def compute_neus_alphas(self, ray_unit, sdfs, gradients, dists, dist_far=None, progress=1., eps=1e-5):
        sdfs = sdfs[..., 0]  # [B,R,N]
        # SDF volume rendering in NeuS.
        inv_s = self.s_var.exp()
        true_cos = (ray_unit[..., None, :] * gradients).sum(dim=-1, keepdim=False)  # [B,R,N]
        iter_cos = self._get_iter_cos(true_cos, progress=progress)  # [B,R,N]
        # Estimate signed distances at section points
        if dist_far is None:
            dist_far = torch.empty_like(dists[..., :1, :]).fill_(1e10)  # [B,R,1,1]
        dists = torch.cat([dists, dist_far], dim=2)  # [B,R,N+1,1]
        dist_intvs = dists[..., 1:, 0] - dists[..., :-1, 0]  # [B,R,N]
        est_prev_sdf = sdfs - iter_cos * dist_intvs * 0.5  # [B,R,N]
        est_next_sdf = sdfs + iter_cos * dist_intvs * 0.5  # [B,R,N]
        prev_cdf = (est_prev_sdf * inv_s).sigmoid()  # [B,R,N]
        next_cdf = (est_next_sdf * inv_s).sigmoid()  # [B,R,N]
        alphas = ((prev_cdf - next_cdf) / (prev_cdf + eps)).clip_(0.0, 1.0)  # [B,R,N]
        # weights = render.alpha_compositing_weights(alphas)  # [B,R,N,1]
        return alphas

    def _get_iter_cos(self, true_cos, progress=1.):
        anneal_ratio = min(progress / self.anneal_end, 1.)
        # The anneal strategy below keeps the cos value alive at the beginning of training iterations.
        return -((-true_cos * 0.5 + 0.5).relu() * (1.0 - anneal_ratio) +
                 (-true_cos).relu() * anneal_ratio)  # always non-positive


class OldModel(BaseModel):

    def __init__(self, cfg_model, cfg_data):
        super().__init__(cfg_model, cfg_data)
        self.cfg_render = cfg_model.render
        self.white_background = cfg_model.background.white
        self.with_background = cfg_model.background.enabled
        self.with_appear_embed = cfg_model.appear_embed.enabled
        self.anneal_end = cfg_model.object.s_var.anneal_end
        self.outside_val = 1000. * (-1 if cfg_model.object.sdf.mlp.inside_out else 1)
        self.image_size_train = cfg_data.train.image_size
        self.image_size_val = cfg_data.val.image_size
        # Define models.
        self.build_model(cfg_model, cfg_data)
        # Define functions.
        self.ray_generator = partial(nerf_util.ray_generator,
                                     camera_ndc=False,
                                     num_rays=cfg_model.render.rand_rays)
        self.sample_dists_from_pdf = partial(nerf_util.sample_dists_from_pdf,
                                             intvs_fine=cfg_model.render.num_samples.fine)
        self.to_full_val_image = partial(misc.to_full_image, image_size=cfg_data.val.image_size)

    def build_model(self, cfg_model, cfg_data):
        # appearance encoding
        if cfg_model.appear_embed.enabled:
            assert cfg_data.num_images is not None
            self.appear_embed = torch.nn.Embedding(cfg_data.num_images, cfg_model.appear_embed.dim)
            if cfg_model.background.enabled:
                self.appear_embed_outside = torch.nn.Embedding(cfg_data.num_images, cfg_model.appear_embed.dim)
            else:
                self.appear_embed_outside = None
        else:
            self.appear_embed = self.appear_embed_outside = None
        self.neural_sdf = NeuralSDF(cfg_model.object.sdf)
        self.neural_rgb = NeuralRGB(cfg_model.object.rgb, feat_dim=cfg_model.object.sdf.mlp.hidden_dim,
                                    appear_embed=cfg_model.appear_embed)
        if cfg_model.background.enabled:
            self.background_nerf = BackgroundNeRF(cfg_model.background, appear_embed=cfg_model.appear_embed)
        else:
            self.background_nerf = None
        self.s_var = torch.nn.Parameter(torch.tensor(cfg_model.object.s_var.init_val, dtype=torch.float32))

    def forward(self, data):
        # Randomly sample and render the pixels.
        output = self.render_pixels(data["pose"], data["intr"], image_size=self.image_size_train,
                                    stratified=self.cfg_render.stratified, sample_idx=data["idx"],
                                    ray_idx=data["ray_idx"])
        return output

    @torch.no_grad()
    def inference(self, data):
        self.eval()
        # Render the full images.
        output = self.render_image(data["pose"], data["intr"], image_size=self.image_size_val,
                                   stratified=False, sample_idx=data["idx"])  # [B,N,C]
        # Get full rendered RGB and depth images.
        rot = data["pose"][..., :3, :3]  # [B,3,3]
        normal_cam = -output["gradient"] @ rot.transpose(-1, -2)  # [B,HW,3]
        output.update(
            rgb_map=self.to_full_val_image(output["rgb"]),  # [B,3,H,W]
            opacity_map=self.to_full_val_image(output["opacity"]),  # [B,1,H,W]
            depth_map=self.to_full_val_image(output["depth"]),  # [B,1,H,W]
            normal_map=self.to_full_val_image(normal_cam),  # [B,3,H,W]
        )
        return output

    def render_image(self, pose, intr, image_size, stratified=False, sample_idx=None):
        """ Render the rays given the camera intrinsics and poses.
        Args:
            pose (tensor [batch,3,4]): Camera poses ([R,t]).
            intr (tensor [batch,3,3]): Camera intrinsics.
            stratified (bool): Whether to stratify the depth sampling.
            sample_idx (tensor [batch]): Data sample index.
        Returns:
            output: A dictionary containing the outputs.
        """
        output = defaultdict(list)
        for center, ray, _ in self.ray_generator(pose, intr, image_size, full_image=True):
            ray_unit = torch_F.normalize(ray, dim=-1)  # [B,R,3]
            output_batch = self.render_rays(center, ray_unit, sample_idx=sample_idx, stratified=stratified)
            if not self.training:
                dist = render.composite(output_batch["dists"], output_batch["weights"])  # [B,R,1]
                depth = dist / ray.norm(dim=-1, keepdim=True)
                output_batch.update(depth=depth)
            for key, value in output_batch.items():
                if value is not None:
                    output[key].append(value.detach())
        # Concat each item (list) in output into one tensor. Concatenate along the ray dimension (1)
        for key, value in output.items():
            output[key] = torch.cat(value, dim=1)
        return output

    def render_pixels(self, pose, intr, image_size, stratified=False, sample_idx=None, ray_idx=None):
        center, ray = camera.get_center_and_ray(pose, intr, image_size)  # [B,HW,3]
        center = nerf_util.slice_by_ray_idx(center, ray_idx)  # [B,R,3]
        ray = nerf_util.slice_by_ray_idx(ray, ray_idx)  # [B,R,3]
        ray_unit = torch_F.normalize(ray, dim=-1)  # [B,R,3]
        output = self.render_rays(center, ray_unit, sample_idx=sample_idx, stratified=stratified)
        return output

    def render_rays(self, center, ray_unit, sample_idx=None, stratified=False):
        with torch.no_grad():
            near, far, outside = self.get_dist_bounds(center, ray_unit)
        app, app_outside = self.get_appearance_embedding(sample_idx, ray_unit.shape[1])
        output_object = self.render_rays_object(center, ray_unit, near, far, outside, app, stratified=stratified)
        if self.with_background:
            output_background = self.render_rays_background(center, ray_unit, far, app_outside, stratified=stratified)
            # Concatenate object and background samples.
            rgbs = torch.cat([output_object["rgbs"], output_background["rgbs"]], dim=2)  # [B,R,No+Nb,3]
            dists = torch.cat([output_object["dists"], output_background["dists"]], dim=2)  # [B,R,No+Nb,1]
            alphas = torch.cat([output_object["alphas"], output_background["alphas"]], dim=2)  # [B,R,No+Nb]
        else:
            rgbs = output_object["rgbs"]  # [B,R,No,3]
            dists = output_object["dists"]  # [B,R,No,1]
            alphas = output_object["alphas"]  # [B,R,No]
        weights = render.alpha_compositing_weights(alphas)  # [B,R,No+Nb,1]
        # Compute weights and composite samples.
        rgb = render.composite(rgbs, weights)  # [B,R,3]
        if self.white_background:
            opacity_all = render.composite(1., weights)  # [B,R,1]
            rgb = rgb + (1 - opacity_all)
        # Collect output.
        output = dict(
            rgb=rgb,  # [B,R,3]
            opacity=output_object["opacity"],  # [B,R,1]/None
            outside=outside,  # [B,R,1]
            dists=dists,  # [B,R,No+Nb,1]
            weights=weights,  # [B,R,No+Nb,1]
            gradient=output_object["gradient"],  # [B,R,3]/None
            gradients=output_object["gradients"],  # [B,R,No,3]
            hessians=output_object["hessians"],  # [B,R,No,3]/None
        )
        return output

    def render_rays_object(self, center, ray_unit, near, far, outside, app, stratified=False):
        with torch.no_grad():
            dists = self.sample_dists_all(center, ray_unit, near, far, stratified=stratified)  # [B,R,N,3]
        points = camera.get_3D_points_from_dist(center, ray_unit, dists)  # [B,R,N,3]
        sdfs, feats = self.neural_sdf.forward(points)  # [B,R,N,1],[B,R,N,K]
        sdfs[outside[..., None].expand_as(sdfs)] = self.outside_val
        # Compute 1st- and 2nd-order gradients.
        rays_unit = ray_unit[..., None, :].expand_as(points).contiguous()  # [B,R,N,3]
        gradients, hessians = self.neural_sdf.compute_gradients(points, training=self.training, sdf=sdfs)
        normals = torch_F.normalize(gradients, dim=-1)  # [B,R,N,3]
        rgbs = self.neural_rgb.forward(points, normals, rays_unit, feats, app=app)  # [B,R,N,3]
        # SDF volume rendering.
        alphas = self.compute_neus_alphas(ray_unit, sdfs, gradients, dists, dist_far=far[..., None],
                                          progress=self.progress)  # [B,R,N]
        if not self.training:
            weights = render.alpha_compositing_weights(alphas)  # [B,R,N,1]
            opacity = render.composite(1., weights)  # [B,R,1]
            gradient = render.composite(gradients, weights)  # [B,R,3]
        else:
            opacity = None
            gradient = None
        # Collect output.
        output = dict(
            rgbs=rgbs,  # [B,R,N,3]
            sdfs=sdfs[..., 0],  # [B,R,N]
            dists=dists,  # [B,R,N,1]
            alphas=alphas,  # [B,R,N]
            opacity=opacity,  # [B,R,3]/None
            gradient=gradient,  # [B,R,3]/None
            gradients=gradients,  # [B,R,N,3]
            hessians=hessians,  # [B,R,N,3]/None
        )
        return output

    def render_rays_background(self, center, ray_unit, far, app_outside, stratified=False):
        with torch.no_grad():
            dists = self.sample_dists_background(ray_unit, far, stratified=stratified)
        points = camera.get_3D_points_from_dist(center, ray_unit, dists)  # [B,R,N,3]
        rays_unit = ray_unit[..., None, :].expand_as(points)  # [B,R,N,3]
        rgbs, densities = self.background_nerf.forward(points, rays_unit, app_outside)  # [B,R,N,3]
        alphas = render.volume_rendering_alphas_dist(densities, dists)  # [B,R,N]
        # Collect output.
        output = dict(
            rgbs=rgbs,  # [B,R,3]
            dists=dists,  # [B,R,N,1]
            alphas=alphas,  # [B,R,N]
        )
        return output

    @torch.no_grad()
    def get_dist_bounds(self, center, ray_unit):
        dist_near, dist_far = nerf_util.intersect_with_sphere(center, ray_unit, radius=1.)
        dist_near.relu_()  # Distance (and thus depth) should be non-negative.
        outside = dist_near.isnan()
        dist_near[outside], dist_far[outside] = 1, 1.2  # Dummy distances. Density will be set to 0.
        return dist_near, dist_far, outside

    def get_appearance_embedding(self, sample_idx, num_rays):
        if self.with_appear_embed:
            # Object appearance embedding.
            num_samples_all = self.cfg_render.num_samples.coarse + \
                self.cfg_render.num_samples.fine * self.cfg_render.num_sample_hierarchy
            app = self.appear_embed(sample_idx)[:, None, None]  # [B,1,1,C]
            app = app.expand(-1, num_rays, num_samples_all, -1)  # [B,R,N,C]
            # Background appearance embedding.
            if self.with_background:
                app_outside = self.appear_embed_outside(sample_idx)[:, None, None]  # [B,1,1,C]
                app_outside = app_outside.expand(-1, num_rays, self.cfg_render.num_samples.background, -1)  # [B,R,N,C]
            else:
                app_outside = None
        else:
            app = app_outside = None
        return app, app_outside

    @torch.no_grad()
    def sample_dists_all(self, center, ray_unit, near, far, stratified=False):
        dists = nerf_util.sample_dists(ray_unit.shape[:2], dist_range=(near[..., None], far[..., None]),
                                       intvs=self.cfg_render.num_samples.coarse, stratified=stratified)
        if self.cfg_render.num_sample_hierarchy > 0:
            points = camera.get_3D_points_from_dist(center, ray_unit, dists)  # [B,R,N,3]
            sdfs = self.neural_sdf.sdf(points)  # [B,R,N]
        for h in range(self.cfg_render.num_sample_hierarchy):
            dists_fine = self.sample_dists_hierarchical(dists, sdfs, inv_s=(64 * 2 ** h))  # [B,R,Nf,1]
            dists = torch.cat([dists, dists_fine], dim=2)  # [B,R,N+Nf,1]
            dists, sort_idx = dists.sort(dim=2)
            if h != self.cfg_render.num_sample_hierarchy - 1:
                points_fine = camera.get_3D_points_from_dist(center, ray_unit, dists_fine)  # [B,R,Nf,3]
                sdfs_fine = self.neural_sdf.sdf(points_fine)  # [B,R,Nf]
                sdfs = torch.cat([sdfs, sdfs_fine], dim=2)  # [B,R,N+Nf]
                sdfs = sdfs.gather(dim=2, index=sort_idx.expand_as(sdfs))  # [B,R,N+Nf,1]
        return dists

    def sample_dists_hierarchical(self, dists, sdfs, inv_s, robust=True, eps=1e-5):
        sdfs = sdfs[..., 0]  # [B,R,N]
        prev_sdfs, next_sdfs = sdfs[..., :-1], sdfs[..., 1:]  # [B,R,N-1]
        prev_dists, next_dists = dists[..., :-1, 0], dists[..., 1:, 0]  # [B,R,N-1]
        mid_sdfs = (prev_sdfs + next_sdfs) * 0.5  # [B,R,N-1]
        cos_val = (next_sdfs - prev_sdfs) / (next_dists - prev_dists + 1e-5)  # [B,R,N-1]
        if robust:
            prev_cos_val = torch.cat([torch.zeros_like(cos_val)[..., :1], cos_val[..., :-1]], dim=-1)  # [B,R,N-1]
            cos_val = torch.stack([prev_cos_val, cos_val], dim=-1).min(dim=-1).values  # [B,R,N-1]
        dist_intvs = dists[..., 1:, 0] - dists[..., :-1, 0]  # [B,R,N-1]
        est_prev_sdf = mid_sdfs - cos_val * dist_intvs * 0.5  # [B,R,N-1]
        est_next_sdf = mid_sdfs + cos_val * dist_intvs * 0.5  # [B,R,N-1]
        prev_cdf = (est_prev_sdf * inv_s).sigmoid()  # [B,R,N-1]
        next_cdf = (est_next_sdf * inv_s).sigmoid()  # [B,R,N-1]
        alphas = ((prev_cdf - next_cdf) / (prev_cdf + eps)).clip_(0.0, 1.0)  # [B,R,N-1]
        weights = render.alpha_compositing_weights(alphas)  # [B,R,N-1,1]
        dists_fine = self.sample_dists_from_pdf(dists, weights=weights[..., 0])  # [B,R,Nf,1]
        return dists_fine

    def sample_dists_background(self, ray_unit, far, stratified=False, eps=1e-5):
        inv_dists = nerf_util.sample_dists(ray_unit.shape[:2], dist_range=(1, 0),
                                           intvs=self.cfg_render.num_samples.background, stratified=stratified)
        dists = far[..., None] / (inv_dists + eps)  # [B,R,N,1]
        return dists

    def compute_neus_alphas(self, ray_unit, sdfs, gradients, dists, dist_far=None, progress=1., eps=1e-5):
        sdfs = sdfs[..., 0]  # [B,R,N]
        # SDF volume rendering in NeuS.
        inv_s = self.s_var.exp()
        true_cos = (ray_unit[..., None, :] * gradients).sum(dim=-1, keepdim=False)  # [B,R,N]
        iter_cos = self._get_iter_cos(true_cos, progress=progress)  # [B,R,N]
        # Estimate signed distances at section points
        if dist_far is None:
            dist_far = torch.empty_like(dists[..., :1, :]).fill_(1e10)  # [B,R,1,1]
        dists = torch.cat([dists, dist_far], dim=2)  # [B,R,N+1,1]
        dist_intvs = dists[..., 1:, 0] - dists[..., :-1, 0]  # [B,R,N]
        est_prev_sdf = sdfs - iter_cos * dist_intvs * 0.5  # [B,R,N]
        est_next_sdf = sdfs + iter_cos * dist_intvs * 0.5  # [B,R,N]
        prev_cdf = (est_prev_sdf * inv_s).sigmoid()  # [B,R,N]
        next_cdf = (est_next_sdf * inv_s).sigmoid()  # [B,R,N]
        alphas = ((prev_cdf - next_cdf) / (prev_cdf + eps)).clip_(0.0, 1.0)  # [B,R,N]
        # weights = render.alpha_compositing_weights(alphas)  # [B,R,N,1]
        return alphas

    def _get_iter_cos(self, true_cos, progress=1.):
        anneal_ratio = min(progress / self.anneal_end, 1.)
        # The anneal strategy below keeps the cos value alive at the beginning of training iterations.
        return -((-true_cos * 0.5 + 0.5).relu() * (1.0 - anneal_ratio) +
                 (-true_cos).relu() * anneal_ratio)  # always non-positive
