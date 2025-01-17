import numpy as np
import tensorflow as tf
import gym
import tqdm
import matplotlib.pyplot as plt

physical_devices = tf.config.experimental.list_physical_devices('GPU')
tf.config.experimental.set_memory_growth(physical_devices[0], True)


NUM_STATES = 1000
NUM_ACTIONS = 2
NUM_GROUPS = 100


class RandomWalk:
    def __init__(self, n_states=NUM_STATES, n_action=NUM_ACTIONS):
        self.n_states = n_states
        self.n_actions = n_action
        self.reset()

    def reset(self):
        self.start = self.n_states//2
        self.ends = [0, self.n_states-1]
        self.current = self.start
        self.done = False
        return self.current

    def sample_action(self):
        value = np.random.choice([0, 1])
        return value

    def render(self):
        paths = np.zeros(self.n_states)
        paths[self.current] = 1
        print(paths)

    def step(self, action):
        rnd = int(np.random.uniform(0, 100))
        self.movements = int(rnd) if action == 0 else -1*int(rnd)
        if 0 < self.current + self.movements < self.n_states:
            self.current = np.clip(
                self.current + self.movements, 0, self.n_states-1)
        if self.current == 0:
            self.done = True
            reward = -10
        elif self.current == self.ends[1]:
            self.done = True
            reward = 10
        else:
            reward = -1
        state = self.current
        done = self.done
        return state, reward, done, {}, {}


def get_state_feature(state, num_states=NUM_STATES, num_groups=NUM_GROUPS):
    one_hot_vector = np.zeros(num_groups)
    loc = int(state//(num_states/num_groups))
    one_hot_vector[loc] = 1
    return one_hot_vector


def neural_network(input_shape=(NUM_GROUPS,)):
    inputs = tf.keras.layers.Input(input_shape)
    hidden = tf.keras.layers.Dense(
        16, activation='relu')(inputs)
    output = tf.keras.layers.Dense(1)(hidden)
    model = tf.keras.Model(inputs, output)
    return model


def semi_gradient_td(env, iterations=200):
    alpha = 0.1
    gamma = 0.99
    nn = neural_network()
    optimizer = tf.keras.optimizers.Adam()
    for iter in tqdm.tqdm(range(iterations)):
        done = env.done
        state = env.reset()
        S = get_state_feature(state)
        while not done:
            action = np.random.choice([0, 1])
            state_prime, reward, done, info, _ = env.step(action)
            S_prime = get_state_feature(state_prime)
            with tf.GradientTape(watch_accessed_variables=True, persistent=True) as tape:
                last_value = nn(tf.expand_dims(S, axis=0))
                current_value = nn(tf.expand_dims(S_prime, axis=0))
                delta = tf.square(reward + gamma*current_value - last_value)
            grads = tape.gradient(delta, nn.trainable_variables)
            optimizer.apply_gradients(zip(grads, nn.trainable_variables))
            state = state_prime
    nn.save_weights('nn.h5')


if __name__ == '__main__':
    env = RandomWalk()
    semi_gradient_td(env)
    nn = neural_network()
    nn.load_weights('nn.h5')

    states = np.array([get_state_feature(i) for i in range(NUM_GROUPS)])
    print(states.shape)
    state_values = nn(states)
    plt.plot(state_values)
    plt.show()
