import numpy as np
import logging

from somber.batch.som import Som
from somber.utils import expo, progressbar


logger = logging.getLogger(__name__)


class Recursive(Som):

    def __init__(self, map_dim, dim, learning_rate, alpha, beta, sigma=None, lrfunc=expo, nbfunc=expo):

        super().__init__(map_dim, dim, learning_rate, lrfunc, nbfunc, sigma, min_max=np.argmax)
        self.context_weights = np.zeros((self.map_dim, self.map_dim))
        self.alpha = alpha
        self.beta = beta

    def _train_loop(self, X, num_epochs, lr_update_counter, nb_update_counter, context_mask, show_progressbar):
        """
        The train loop. Is a separate function to accomodate easy inheritance.

        :param X: The input data.
        :param lr_update_counter: A list of indices at which the params need to be updated.
        :return: None
        """

        nb_step = 0
        lr_step = 0

        # Calculate the influences for update 0.
        map_radius = self.nbfunc(self.sigma, 0, len(nb_update_counter))
        learning_rate = self.lrfunc(self.learning_rate, 0, len(nb_update_counter))
        influences = self._calculate_influence(map_radius)
        update = False

        idx = 0

        for epoch in range(num_epochs):

            prev_activation = np.zeros((X.shape[1], self.map_dim))

            for x, ct in progressbar(zip(X, context_mask), mult=X.shape[1], use=show_progressbar):

                prev_activation = self._example(x, influences, prev_activation=prev_activation)

                prev_activation *= ct

                if idx in nb_update_counter:
                    nb_step += 1

                    map_radius = self.nbfunc(self.sigma, nb_step, len(nb_update_counter))
                    logger.info("Updated map radius: {0}".format(map_radius))
                    update = True

                if idx in lr_update_counter:

                    lr_step += 1

                    learning_rate = self.lrfunc(self.learning_rate, lr_step, len(lr_update_counter))
                    logger.info("Updated learning rate: {0}".format(learning_rate))
                    update = True

                if update:

                    influences = self._calculate_influence(map_radius) * learning_rate
                    update = False

                idx += 1

    def _example(self, x, influences, **kwargs):
        """
        A single epoch.
        :param X: a numpy array of data
        :param map_radius: The radius at the current epoch, given the learning rate and map size
        :param learning_rates: The learning rate.
        :param batch_size: The batch size
        :return: The best matching unit
        """

        prev_activation = kwargs['prev_activation']

        activation, diff_x, diff_context = self._get_bmus(x, prev_activation=prev_activation)

        influence, bmu = self._apply_influences(activation, influences)

        # Update
        self.weights += self._calculate_update(diff_x, influence).mean(axis=0)
        # print(influence.shape)
        self.context_weights += self._calculate_update(diff_context, influence).mean(axis=0)

        return activation

    def _create_batches(self, X, batch_size):
        """
        Creates batches out of a sequential piece of data.
        Assumes ndim(X) == 2.

        This function will append zeros to the end of your data to make all batches even-sized.

        For the recursive SOM, this function does not simply resize your data. It will create
        subsequences.

        :param X: A numpy array, representing your input data. Must have 2 dimensions.
        :param batch_size: The desired batch size.
        :return: A batched version of your data.
        """

        # This line first resizes the data to (batch_size, len(X) / batch_size, data_dim)
        X = np.resize(X, (batch_size, int(np.ceil(X.shape[0] / batch_size)), X.shape[1]))
        # Transposes it to (len(X) / batch_size, batch_size, data_dim)
        return X.transpose((1, 0, 2))

    def _get_bmus(self, x, **kwargs):
        """
        Gets the best matching units, based on euclidean distance.
        :param x: The input vector
        :return: An integer, representing the index of the best matching unit.
        """

        prev_activation = kwargs['prev_activation']

        # Differences is the components of the weights subtracted from the weight vector.
        difference_x = self._distance_difference(x, self.weights)
        difference_y = self._distance_difference(prev_activation, self.context_weights)

        # Distances are squared euclidean norm of differences.
        # Since euclidean norm is sqrt(sum(square(x)))) we can leave out the sqrt
        # and avoid doing an extra square.
        distance_x = self._euclidean(x, self.weights)
        distance_y = self._euclidean(prev_activation, self.context_weights)

        activation = np.exp(-(self.alpha * distance_x + self.beta * distance_y))

        return activation, difference_x, difference_y

    def _predict_base(self, X):
        """
        Predicts distances to some input data.

        :param X: The input data.
        :return: An array of arrays, representing the activation
        each node has to each input.
        """

        X = self._create_batches(X, 1)

        # Return the indices of the BMU which matches the input data most
        distances = []

        prev_activation = np.sum(np.square(self._distance_difference(X[0], self.weights)), axis=2)
        distances.extend(prev_activation)

        for x in X[1:]:
            prev_activation, _, _ = self._get_bmus(x, prev_activation=prev_activation)
            distances.extend(prev_activation)

        return np.array(distances)