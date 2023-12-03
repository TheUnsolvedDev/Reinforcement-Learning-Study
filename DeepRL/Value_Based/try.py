import tensorflow as tf
import numpy as np
import gymnasium as gym
import tqdm
import sys

physical_devices = tf.config.experimental.list_physical_devices()
tf.config.experimental.set_memory_growth(physical_devices[1], True)
env = gym.make("CartPole-v1", max_episode_steps=1000)
BUFFER_SIZE = 10_000
NUM_TRAIN_STEPS = 250_000
MIN_BUFFER_SIZE = 1_000
BATCH_SIZE = 64
TARGET_UPDATE = 100
Q_UPDATE = 1
TAU = 1
ALPHA = 0.00025
GAMMA = 0.99
DELTA = 1
EPSILON = 1
MIN_EPSILON = 0.025
NUM_ACTIONS = env.action_space.n
OBSERVATION_SHAPE = env.observation_space.shape


class QModel(tf.keras.Model):
    def __init__(self, name='Model'):
        super(QModel, self).__init__()
        self.flatten = tf.keras.layers.Flatten()
        self.deep_layer1 = tf.keras.layers.Dense(32, activation='relu')
        self.deep_layer2 = tf.keras.layers.Dense(16, activation='relu')
        self.final = tf.keras.layers.Dense(NUM_ACTIONS, activation='linear')

    def call(self, x):
        x = self.flatten(x)
        x = self.deep_layer1(x)
        x = self.deep_layer2(x)
        x = self.final(x)
        return x

    def model(self):
        inputs = tf.keras.layers.Input(shape=OBSERVATION_SHAPE)
        outputs = self(inputs)
        return tf.keras.models.Model(inputs=inputs, outputs=outputs)


class ReplayBuffer:
    def __init__(self, size=BUFFER_SIZE):
        self.capacity = size
        self.storage = {
            'state': np.zeros((self.capacity, OBSERVATION_SHAPE[0])).astype(np.float32),
            'action': np.zeros(self.capacity).astype(np.int32),
            'reward': np.zeros(self.capacity).astype(np.float32),
            'next_state': np.zeros((self.capacity, OBSERVATION_SHAPE[0])).astype(np.float32),
            'done': np.zeros(self.capacity).astype(np.float32)
        }
        self.counter = 0
        self.filled = 0

    def __len__(self):
        return self.filled

    def store_transition(self, transition):
        state, action, reward, next_state, done = transition
        self.storage['state'][self.counter] = state
        self.storage['action'][self.counter] = action
        self.storage['reward'][self.counter] = reward
        self.storage['next_state'][self.counter] = next_state
        self.storage['done'][self.counter] = done
        self.counter = (self.counter + 1) % self.capacity
        self.filled = max(self.filled, self.capacity)

    def sample(self, batch_size):
        indices = np.random.randint(
            low=0, high=self.filled, size=batch_size)
        states = self.storage['state'][indices]
        actions = self.storage['action'][indices]
        rewards = self.storage['reward'][indices]
        next_states = self.storage['next_state'][indices]
        dones = self.storage['done'][indices]
        return states, actions, rewards, next_states, dones


class DQNAgent:
    def __init__(self) -> None:
        self.q_model = QModel('q_model')  # .model()
        self.target_model = QModel('target_model')  # .model()
        self.optimizer = tf.keras.optimizers.Adam(ALPHA)
        self.replay_buffer = ReplayBuffer(BUFFER_SIZE)

    @tf.function
    def _greedy_action(self, state):
        state = tf.expand_dims(state, axis=0)
        q_values = self.q_model(state, training=False)
        return tf.argmax(q_values[0])

    def get_actions(self, state, epsilon):
        if np.random.uniform(0, 1) < epsilon:
            return np.random.randint(0, NUM_ACTIONS)
        return self._greedy_action(state).numpy()

    def soft_update(self, tau=TAU):
        target_dqn_weights = self.target_model.get_weights()
        main_dqn_weights = self.q_model.get_weights()
        for i in range(len(target_dqn_weights)):
            main_dqn_weights[i] = tau * main_dqn_weights[i] + \
                (1 - tau) * target_dqn_weights[i]
        self.target_model.set_weights(main_dqn_weights)

    @tf.function
    def td_error(self, transitions):
        states, actions, rewards, next_states, dones = transitions
        # next_q = tf.reduce_max(self.target_model(
        #     next_states, training=False), axis=1)
        # q = tf.reduce_sum(self.q_model(states) *
        #                   tf.one_hot(actions, depth=NUM_ACTIONS), axis=1)
        # return (rewards + (1-dones)*GAMMA*next_q, q)
        indices = tf.range(tf.shape(states)[0], dtype=tf.int32)
        action_indices = tf.stack([indices, actions], axis=1)
        q_pred = tf.gather_nd(self.q_model(states), indices=action_indices)
        q_next = self.target_model(next_states)

        max_actions = tf.argmax(q_next, axis=-1, output_type=tf.int32)
        max_action_indices = tf.stack([indices, max_actions],axis = 1)
        q_target = rewards + GAMMA * \
            tf.gather_nd(q_next, indices=max_action_indices)*(1-dones)
        loss = tf.keras.losses.mean_squared_error(q_target, q_pred)
        return tf.reduce_mean(loss), tf.subtract(q_target, q_pred)

    def train(self, transitions):
        td_error, loss = self._train_step(transitions)
        return td_error, loss

    @tf.function
    def _train_step(self, transitions):
        with tf.GradientTape() as tape:
            loss, td_error = self.td_error(transitions)
            # td_error = target-pred
            # huber_mse = 0.5*tf.keras.losses.mse(target, pred)
            # huber_mae = DELTA * \
            #     (tf.keras.losses.mae(target, pred) - 0.5 * DELTA)
            # loss = tf.where(tf.abs(td_error) <= DELTA, huber_mse, huber_mae)
            # # loss = tf.square(td_error)
            # loss = tf.reduce_mean(loss)
        grads = tape.gradient(loss, self.q_model.trainable_variables)
        self.optimizer.apply_gradients(
            zip(grads, self.q_model.trainable_variables))
        return td_error, loss

    def load(self, path):
        raise NotImplementedError

    def save(self):
        raise NotImplementedError


def linear_schedule(t, start_e=EPSILON, end_e=MIN_EPSILON, duration=NUM_TRAIN_STEPS*0.3):
    slope = (end_e - start_e) / duration
    return max(slope * t + start_e, end_e)


def test_env(agent, num_games=10):
    env = gym.make("CartPole-v1", max_episode_steps=1000)
    rewards = np.zeros(num_games)
    for i in range(num_games):
        state, _ = env.reset()
        while True:
            action = agent.get_actions(state, epsilon=0.01)
            state, reward, done, truncated, info = env.step(action)
            rewards[i] += reward
            if done or truncated:
                break
    return rewards.mean()


def main():
    agent = DQNAgent()
    state, _ = env.reset()
    agent.soft_update()
    epsilon = EPSILON

    for step in tqdm.tqdm(range(NUM_TRAIN_STEPS+1)):
        action = agent.get_actions(state, epsilon)
        next_state, reward, done, truncated, info = env.step(action)
        agent.replay_buffer.store_transition(
            (state, action, reward, next_state, done or truncated))
        state = next_state
        if done or truncated:
            state, _ = env.reset()

        if (step % TARGET_UPDATE) == 0:
            agent.soft_update()

        if (len(agent.replay_buffer) > MIN_BUFFER_SIZE) and not (step % Q_UPDATE):
            epsilon = linear_schedule(step)
            states, actions, rewards, next_states, dones = agent.replay_buffer.sample(
                BATCH_SIZE)
            td_error, loss = agent.train(
                (states, actions, rewards, next_states, dones))

            if (step % 1000 == 0):
                test_rewards = test_env(agent)
                print('\rStep [{0:}/{1:}]\t TD_error: {2:.3f}\t Loss: {3:.3f}\t Epsilon:{4:.3f}\t Rewards:{5:}'.format(step,
                                                                                                                       NUM_TRAIN_STEPS, np.mean(td_error), loss, epsilon, test_rewards))
                sys.stdout.flush()


if __name__ == '__main__':
    main()