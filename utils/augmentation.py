import numpy as np
import torch
from scipy.io import loadmat
from torch import nn
import torch.nn.functional as nnf


class SpatialTransformer(nn.Module):
    def __init__(self):
        super(SpatialTransformer, self).__init__()

    def forward(self, src, flow, mode='bilinear', padding_mode='zeros'):
        shape = flow.shape[2:]
        vectors = [torch.arange(0, s) for s in shape]
        grids = torch.meshgrid(vectors)
        grid = torch.stack(grids)  # y, x, z
        grid = torch.unsqueeze(grid, 0)  # add batch
        grid = grid.type(torch.FloatTensor)

        if torch.cuda.is_available():
            grid = grid.cuda()

        new_locs = grid + flow

        for i in range(len(shape)):
            new_locs[:, i, ...] = 2*(new_locs[:,i,...]/(shape[i]-1) - 0.5)

        if len(shape) == 2:
            new_locs = new_locs.permute(0, 2, 3, 1)
            new_locs = new_locs[..., [1,0]]
        elif len(shape) == 3:
            new_locs = new_locs.permute(0, 2, 3, 4, 1)
            new_locs = new_locs[..., [2,1,0]]

        return nnf.grid_sample(src, new_locs, mode=mode, padding_mode=padding_mode)

class SpatialTransform(object):
    def __init__(self, do_rotation=True, angle_x=(0, 2 * np.pi), angle_y=(0, 2 * np.pi), angle_z=(0, 2 * np.pi),
                 do_scale=True, scale=(0.75, 1.25)):
        self.do_rotation = do_rotation
        self.angle_x = angle_x
        self.angle_y = angle_y
        self.angle_z = angle_z
        self.do_scale = do_scale
        self.scale = scale
        self.stn = SpatialTransformer()

    def augment_spatial(self, data, code, mode='bilinear'):
        data = self.stn(data, code, mode=mode, padding_mode='zeros')
        return data

    def rand_coords(self, patch_size):
        coords = self.create_zero_centered_coordinate_mesh(patch_size)
        if self.do_rotation:
            a_x = np.random.uniform(self.angle_x[0], self.angle_x[1])
            a_y = np.random.uniform(self.angle_y[0], self.angle_y[1])
            a_z = np.random.uniform(self.angle_z[0], self.angle_z[1])

            coords = self.rotate_coords_3d(coords, a_x, a_y, a_z)

        if self.do_scale:
            sc = np.random.uniform(self.scale[0], self.scale[1])
            coords = self.scale_coords(coords, sc)

        ctr = np.asarray([patch_size[0]//2, patch_size[1]//2, patch_size[2]//2])
        grid = np.where(np.ones(patch_size)==1)
        grid = np.concatenate([grid[0].reshape((1,)+patch_size), grid[1].reshape((1,)+patch_size), grid[2].reshape((1,)+patch_size)], axis=0)
        grid = grid.astype(np.float32)

        coords += ctr[:, np.newaxis, np.newaxis, np.newaxis] - grid
        coords = coords.astype(np.float32)
        coords = torch.from_numpy(coords[np.newaxis, :, :, :, :])
        if torch.cuda.is_available():
            coords = coords.cuda()
        return coords

    def create_zero_centered_coordinate_mesh(self, shape):
        tmp = tuple([np.arange(i) for i in shape])
        coords = np.array(np.meshgrid(*tmp, indexing='ij')).astype(float)
        for d in range(len(shape)):
            coords[d] -= ((np.array(shape).astype(float) - 1) / 2.)[d]
        return coords

    def rotate_coords_3d(self, coords, angle_x, angle_y, angle_z):
        rot_matrix = np.identity(len(coords))

        rotation_x = np.array([[1, 0, 0], [0, np.cos(angle_x), -np.sin(angle_x)], [0, np.sin(angle_x), np.cos(angle_x)]])
        rot_matrix = np.dot(rot_matrix, rotation_x)
        rotation_y = np.array([[np.cos(angle_y), 0, np.sin(angle_y)], [0, 1, 0], [-np.sin(angle_y), 0, np.cos(angle_y)]])
        rot_matrix = np.dot(rot_matrix, rotation_y)
        rotation_z = np.array([[np.cos(angle_z), -np.sin(angle_z), 0], [np.sin(angle_z), np.cos(angle_z), 0], [0, 0, 1]])
        rot_matrix = np.dot(rot_matrix, rotation_z)

        coords = np.dot(coords.reshape(len(coords), -1).transpose(), rot_matrix).transpose().reshape(coords.shape)
        return coords

    def scale_coords(self, coords, scale):
        if isinstance(scale, (tuple, list, np.ndarray)):
            assert len(scale) == len(coords)
            for i in range(len(scale)):
                coords[i] *= scale[i]
        else:
            coords *= scale
        return coords
