import numpy as np
import matplotlib.pyplot as plt
import gym
import tensorflow as tf
import tensorflow_probability as tfp

env = gym.make('CartPole-v0', max_episode_steps=500)
env.reward_threshold=500
test_env = gym.make('CartPole-v1', render_mode='human')

gamma = 0.99
in_dim = env.observation_space.shape[0]
out_dim = env.action_space.n

physical_devices = tf.config.experimental.list_physical_devices('GPU')
tf.config.experimental.set_memory_growth(physical_devices[0], True)


def model(in_dim=in_dim, out_dim=out_dim):
    inputs = tf.keras.layers.Input(in_dim)
    hidden = tf.keras.layers.Dense(64, activation='relu')(inputs)
    hidden1 = tf.keras.layers.Dense(32, activation='relu')(hidden)
    outputs = tf.keras.layers.Dense(out_dim, activation='linear')(hidden1)
    return tf.keras.Model(inputs, outputs)


class BaselineNet():
    def __init__(self, input_size, output_size):
        self.model = tf.keras.Sequential(
            layers=[
                tf.keras.layers.Input(shape=(input_size,)),
                tf.keras.layers.Dense(
                    64, activation="relu", name="relu_layer"),
                tf.keras.layers.Dense(output_size, activation="linear",
                                      name="linear_layer")
            ],
            name="baseline")
        self.optimizer = tf.keras.optimizers.Adam(learning_rate=0.001)

    def forward(self, observations):
        observations = np.array(observations)
        output = tf.squeeze(self.model(observations))
        return output

    def update(self, observations, target):
        with tf.GradientTape() as tape:
            predictions = self.forward(observations)
            loss = tf.keras.losses.mean_squared_error(
                y_true=target, y_pred=predictions)
        grads = tape.gradient(loss, self.model.trainable_weights)
        self.optimizer.apply_gradients(
            zip(grads, self.model.trainable_weights))


class agent:
    def __init__(self) -> None:
        self.model = model(in_dim, out_dim)
        self.baseline_net = BaselineNet(in_dim, 1)
        self.opt = tf.keras.optimizers.Adam(learning_rate=0.001)

    def act(self, state):
        prob = self.model(np.array([state]))
        categorical = tfp.distributions.Categorical(logits=prob)
        action = categorical.sample()
        return int(action.numpy()[0])

    @tf.function
    def a_loss(self, prob, action, reward):
        dist = tfp.distributions.Categorical(logits=prob, dtype=tf.float32)
        log_prob = dist.log_prob(action)
        loss = -log_prob*tf.cast(reward, dtype=tf.float32)
        return tf.reduce_mean(loss)

    def get_advantage(self, returns, observations):
        values = self.baseline_net.forward(observations).numpy()
        advantages = returns - values
        advantages = (advantages-np.mean(advantages)) / \
            np.sqrt(np.sum(advantages**2))
        return advantages

    def discounted_reward(self, rewards):
        discnt_rewards = []
        sum_reward = 0
        rewards.reverse()
        for r in rewards:
            sum_reward = r + gamma*sum_reward
            discnt_rewards.append(sum_reward)
        discnt_rewards.reverse()
        return discnt_rewards

    # @tf.function
    def train(self, states, rewards, actions):
        discnt_rewards = self.discounted_reward(rewards)
        advantages = self.get_advantage(discnt_rewards, states)
        self.baseline_net.update(observations=states, target=discnt_rewards)

        with tf.GradientTape() as tape:
            p = self.model(np.array(states), training=True)
            loss = self.a_loss(p, actions, advantages)
        grads = tape.gradient(loss, self.model.trainable_variables)
        self.opt.apply_gradients(
            zip(grads, self.model.trainable_variables))


def plot(scores, mean_scores):
    plt.ion()
    plt.clf()
    plt.title('Training Reinforce.')
    plt.xlabel('Number of Games')
    plt.ylabel('Score')
    plt.plot(scores)
    plt.plot(mean_scores)
    plt.ylim(ymin=0)
    plt.text(len(scores)-1, scores[-1], str(scores[-1]))
    plt.text(len(mean_scores)-1, mean_scores[-1], str(mean_scores[-1]))
    plt.show(block=False)
    plt.pause(0.001)
    plt.savefig('TrainingAndInferenceReinforceBaseline.png')


def main():
    agentoo7 = agent()
    total_rewards = []
    mean_rewards = []
    for game in range(1000):
        state = env.reset()[0]
        total_reward = 0
        rewards = []
        states = []
        actions = []
        done = False
        while not done:
            action = agentoo7.act(state)
            next_state, reward, done, info, _ = env.step(action)
            rewards.append(reward)
            states.append(state)
            actions.append(action)
            state = next_state
            total_reward += reward

            if done:
                agentoo7.train(states, rewards, actions)
                print("total reward after {} steps is {}".format(
                    game, total_reward))

        total_rewards.append(total_reward)
        avg_reward = np.mean(total_rewards)
        if total_reward > avg_reward:
            agentoo7.model.save_weights('reinforce_model_baseline.h5')
            print('...model save success...')

        mean_rewards.append(avg_reward)
        plot(total_rewards, mean_rewards)


if __name__ == '__main__':
    main()
