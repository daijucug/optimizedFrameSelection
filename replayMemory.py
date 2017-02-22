import numpy as np
import threading as th
import random
import time

class ReplayMemory:
    def __init__(self, config):
        self.capacity = config.replay_memory_capacity
        self.batch_size = config.batch_size
        self.buff_size = config.buff_size
        self.screens = np.empty((self.capacity, 84,84), dtype=np.uint8)
        self.actions = np.empty((self.capacity), dtype=np.uint8)
        self.rewards = np.empty((self.capacity), dtype=np.int8)
        self.terminals = np.empty((self.capacity), dtype=np.bool)
        self.next_state_batch = np.empty((self.batch_size, 84, 84, 4), dtype=np.uint8)
        self.state_batch = np.empty((self.batch_size, 84, 84, 4), dtype=np.uint8)
        self.current = 0
        self.step = 0
        self.filled = False

        self.lock = th.Lock()

        self.cache_full = th.Event()
        self.cache_empty = th.Event()
        self.cache_empty.set()
        self.stop_caching = False
        self.cache_thread = th.Thread(target=self.cache_loop)
        self.cache_thread.setDaemon(True)
        self.cache_thread.start()

    def add(self, screen, action, reward, terminal):
        self.lock.acquire()
        self.screens[self.current] = screen
        self.actions[self.current] = action
        self.rewards[self.current] = reward
        self.terminals[self.current] = terminal
        self.lock.release()
        self.current += 1
        self.step += 1
        if self.current == self.capacity:
            self.current = 0
            self.filled = True

    def get_state(self, index):
        if self.filled == False:
            assert index < self.current, "%i index has note been added yet"%index
        #Fast slice read
        if index >= self.buff_size - 1:
            state = self.screens[(index - self.buff_size+1):(index + 1), ...]
        #Slow list read
        else:
            indexes = [(index - i) % self.capacity for i in reversed(range(self.buff_size))]
            state = self.screens[indexes, ...]
        # different screens should be in the 3rd dim as channels
        return np.transpose(state, [1,2,0])

    def sample_transition_batch(self):
        if self.filled == False:
          assert self.current >= self.batch_size, "There are to few samples. At least add() batch_size times"
        self.cache_full.wait()
        transition_ba = [self.state_batch.copy(), self.action_batch, self.reward_batch, self.next_state_batch.copy(), self.terminal_batch, self.indexes]
        self.cache_full.clear()
        self.cache_empty.set()
        return transition_ba

    def cache_transition_batch(self):
        self.lock.acquire()
        indexes = []
        while len(indexes) != self.batch_size:
            # index, is the index of state, and index + 1 of next_state
            if self.filled:
                index = random.randint(0, self.capacity - 2) # -2 because index +1 will be used for next state
                # if index is in the space we are currently writing
                if index >= self.current and index - self.buff_size <= self.current:
                    continue
            else:
                # can't start from 0 because get_state would loop back to the end -- wich is uninitialized.
                # index +1 can be terminal
                index = random.randint(self.buff_size -1, self.current -2)

            if self.terminals[(index - self.buff_size):index].any():
                continue
            self.state_batch[len(indexes)] = self.get_state(index)
            self.next_state_batch[len(indexes)] = self.get_state(index + 1)
            indexes.append(index)

        self.action_batch = self.actions[indexes]
        self.reward_batch = self.rewards[indexes]
        self.terminal_batch = self.terminals[indexes]
        self.indexes = indexes
        self.lock.release()

    def cache_loop(self):
        # until there is a reasonable number of samples
        while self.current < self.batch_size:
            time.sleep(0.5)
        # start caching
        while self.stop_caching == False:
            self.cache_empty.wait()
            self.cache_transition_batch()
            self.cache_full.set()
            self.cache_empty.clear()

    def __del__(self):
        self.stop_cache = True
        self.cache_thread.join()
