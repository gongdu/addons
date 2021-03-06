# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import abc
import six

import tensorflow as tf


@six.add_metaclass(abc.ABCMeta)
class AveragedOptimizerWrapper(tf.keras.optimizers.Optimizer):
    def __init__(self,
                 optimizer,
                 sequential_update=True,
                 name="AverageOptimizer",
                 **kwargs):
        super(AveragedOptimizerWrapper, self).__init__(name, **kwargs)

        if isinstance(optimizer, str):
            optimizer = tf.keras.optimizers.get(optimizer)

        if not isinstance(optimizer, tf.keras.optimizers.Optimizer):
            raise TypeError(
                'optimizer is not an object of tf.keras.optimizers.Optimizer')

        if not isinstance(sequential_update, bool):
            raise TypeError("sequential_update must be of bool type")

        self._optimizer = optimizer
        self._sequential_update = sequential_update

    def _create_slots(self, var_list):
        self._optimizer._create_slots(var_list=var_list)  # pylint: disable=protected-access
        for var in var_list:
            self.add_slot(var, 'average')

    def _create_hypers(self):
        self._optimizer._create_hypers()  # pylint: disable=protected-access

    def _prepare(self, var_list):
        return self._optimizer._prepare(var_list=var_list)  # pylint: disable=protected-access

    def apply_gradients(self, grads_and_vars, name=None):
        self._optimizer._iterations = self.iterations  # pylint: disable=protected-access
        return super(AveragedOptimizerWrapper, self).apply_gradients(
            grads_and_vars, name)

    @abc.abstractmethod
    def average_op(self, var, average_var):
        raise NotImplementedError

    def _apply_average_op(self, train_op, var):
        average_var = self.get_slot(var, 'average')
        if self._sequential_update:
            with tf.control_dependencies([train_op]):
                avg_op = self.average_op(var, average_var)
        else:
            avg_op = self.average_op(var, average_var)

        return avg_op

    def _resource_apply_dense(self, grad, var):
        train_op = self._optimizer._resource_apply_dense(grad, var)  # pylint: disable=protected-access
        average_op = self._apply_average_op(train_op, var)
        return tf.group(train_op, average_op)

    def _resource_apply_sparse(self, grad, var, indices):
        train_op = self._optimizer._resource_apply_sparse(  # pylint: disable=protected-access
            grad, var, indices)
        average_op = self._apply_average_op(train_op, var)
        return tf.group(train_op, average_op)

    def _resource_apply_sparse_duplicate_indices(self, grad, var, indices):
        train_op = self._optimizer._resource_apply_sparse_duplicate_indices(  # pylint: disable=protected-access
            grad, var, indices)
        average_op = self._apply_average_op(train_op, var)
        return tf.group(train_op, average_op)

    def assign_average_vars(self, var_list):
        """Assign variables in var_list with their respective averages.

        Args:
            var_list: List of model variables to be assigned to their average.

        Returns:
            assign_op: The op corresponding to the assignment operation of
            variables to their average.

        Example:
        ```python
        model = tf.Sequential([...])
        opt = tfa.optimizers.SWA(
                tf.keras.optimizers.SGD(lr=2.0), 100, 10)
        model.compile(opt, ...)
        model.fit(x, y, ...)

        # Update the weights to their mean before saving
        opt.assign_average_vars(model.variables)

        model.save('model.h5')
        ```
        """
        assign_op = tf.group([
            var.assign(self.get_slot(var, 'average')) for var in var_list
            if var.trainable
        ])
        return assign_op

    def get_config(self):
        config = {
            'optimizer': tf.keras.optimizers.serialize(self._optimizer),
            'sequential_update': self._sequential_update
        }
        base_config = super(AveragedOptimizerWrapper, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

    @classmethod
    def from_config(cls, config, custom_objects=None):
        optimizer = tf.keras.optimizers.deserialize(
            config.pop('optimizer'),
            custom_objects=custom_objects,
        )
        return cls(optimizer, **config)

    @property
    def weights(self):
        return self._weights + self._optimizer.weights

    @property
    def lr(self):
        return self._optimizer._get_hyper('learning_rate')  # pylint: disable=protected-access

    @lr.setter
    def lr(self, lr):
        self._optimizer._set_hyper('learning_rate', lr)  # pylint: disable=protected-access

    @property
    def learning_rate(self):
        return self._optimizer._get_hyper('learning_rate')  # pylint: disable=protected-access

    @learning_rate.setter
    def learning_rate(self, learning_rate):
        self._optimizer._set_hyper('learning_rate', learning_rate)  # pylint: disable=protected-access
