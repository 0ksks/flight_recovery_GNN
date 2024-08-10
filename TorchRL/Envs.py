from torchrl.envs import EnvBase
from torchrl.data import (
    UnboundedContinuousTensorSpec,
    CompositeSpec,
    OneHotDiscreteTensorSpec,
)
from typing import Union
from collections import defaultdict
import numpy as np
import torch as th
from tensordict import TensorDict


class DAGenv(EnvBase):
    def __init__(
        self,
        adj_list: dict[int, Union[list[int], np.ndarray, th.Tensor]],
        reward=1,
        device=th.device("cpu"),
        th_dtype=th.float32,
        np_dtype=np.float32,
    ):
        super(DAGenv, self).__init__()
        self.th_dtype = th_dtype
        self.np_dtype = np_dtype
        self.adj_list = adj_list
        self.state_size = len(self.adj_list)
        self.action_size = self.state_size
        self.reward = reward
        self.state = np.zeros(self.state_size).astype(bool)
        self.device = device
        observation_spec = OneHotDiscreteTensorSpec(
            self.state_size, shape=th.Size([self.state_size])
        )
        self.observation_spec = CompositeSpec(observation=observation_spec)
        self.action_spec = OneHotDiscreteTensorSpec(
            self.action_size, shape=th.Size([self.action_size])
        )
        self.reward_spec = UnboundedContinuousTensorSpec(shape=th.Size([1]))

    def _reset(self, tensordict, **kwargs):
        obs_tensordict = TensorDict({}, batch_size=th.Size())
        self.state = np.zeros(self.state_size).astype(bool)
        obs_tensordict.set(
            "observation", th.tensor(self.state.flatten(), device=self.device)
        )
        return obs_tensordict

    def _step(self, tensordict):
        action = tensordict["action"]
        action: np.ndarray = action.cpu().detach().numpy().reshape(-1)
        visited = self.state.copy()
        updated = self.visit(action)
        terminated = self.avail_next(np.argwhere(action == True).item()).size == 0
        if updated:
            reward = [
                self.reward if action_ and not visited_ else 0
                for action_, visited_ in zip(action, visited)
            ]
        else:
            reward = [0 for _ in action]
        step_tensordict = TensorDict(
            {
                "observation": th.tensor(
                    self.state.astype(self.np_dtype).flatten(), device=self.device
                ),
                "reward": th.tensor(
                    sum(reward), dtype=self.th_dtype, device=self.device
                ),
                "done": th.tensor(terminated, dtype=th.bool, device=self.device),
            },
            batch_size=th.Size(),
        )
        return step_tensordict

    def _set_seed(self, seed):
        pass

    @staticmethod
    def edge_idx_2_adj_list(
        edge_idx: list[list[int]],
    ) -> dict[int, Union[list[int], np.ndarray, th.Tensor]]:
        adj_list = defaultdict(list)
        cols = len(edge_idx[0])
        for i in range(cols):
            adj_list[edge_idx[0][i]].append(edge_idx[1][i])
        adj_list = dict(adj_list)
        for i in range(cols):
            if edge_idx[1][i] not in adj_list.keys():
                adj_list[edge_idx[1][i]] = []
        return adj_list

    @staticmethod
    def np_array_adj_list(adj_list: dict[int, list[int]]):
        adj_list_array: dict[int, np.ndarray] = {}
        for k, v in adj_list.items():
            adj_list_array[k] = np.array(v).astype(int)
        return adj_list_array

    def visit(self, state) -> bool:
        updated = not self.state[np.argwhere(state == 1)].all()
        self.state[state] = True
        return updated

    def avail_next(self, state_idx: int) -> np.ndarray:
        all_next = self.adj_list[state_idx]
        return all_next[~self.state[all_next]]

    def get_state(self):
        """visited state list[bool]"""
        return self.state