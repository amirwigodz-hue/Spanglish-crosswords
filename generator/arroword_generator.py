"""
Arroword (arrow-word crossword) generator.

Each answer gets a clue block ('#') right before its first letter:
  - Horizontal ('H') word: clue block is directly to the LEFT of the word.
  - Vertical   ('V') word: clue block is directly ABOVE the word.

Usage:
    from arroword_generator import ArrowordGenerator
    from vocab import VOCAB

    gen = ArrowordGenerator(width=10, height=16, seed=42)
    gen.generate(VOCAB, attempts=60)
    gen.print_grid()
    data = gen.to_dict()      # ready for json.dumps -> your website
"""

from __future__ import annotations

import json
import random
import unicodedata
from collections import defaultdict

EMPTY = ' '
BLOCK = '#'
DIRS = ('H', 'V')


class ArrowordGenerator:
    def __init__(self, width=10, height=16, min_word_len=2,
                 shared_clue_blocks=False, unique_clues=True, seed=None):
        """
        width, height       grid size (columns, rows)
        min_word_len        shortest answer allowed (1-letter answers look odd)
        shared_clue_blocks  if True, one '#' may hold two clues (one pointing
                            right, one pointing down) like printed arrowords.
                            False = one clue per block (your original rule).
        unique_clues        never show the same clue twice in one puzzle
                            (e.g. 'casa' for both HOME and HOUSE is ambiguous)
        seed                set for reproducible puzzles (e.g. a daily puzzle)
        """
        self.width = width
        self.height = height
        self.min_word_len = min_word_len
        self.shared_clue_blocks = shared_clue_blocks
        self.unique_clues = unique_clues
        self.rng = random.Random(seed)
        self._reset()

    # ------------------------------------------------------------------ state
    def _reset(self):
        self.grid = [[EMPTY] * self.width for _ in range(self.height)]
        self.placed_words = []
        # (r, c) -> set of directions of words running through this letter
        self._cell_dirs = defaultdict(set)
        # (r, c) -> set of directions of clues stored in this block
        self._block_dirs = defaultdict(set)
        self._used_words = set()
        self._used_clues = set()

    # ------------------------------------------------------------ vocabulary
    @staticmethod
    def normalize_answer(text):
        """'Be able ' -> 'beable', 'Café' -> 'cafe'. Keeps only a-z."""
        text = unicodedata.normalize('NFKD', text)
        return ''.join(ch for ch in text.lower() if 'a' <= ch <= 'z')

    def prepare_vocab(self, word_dict):
        """Normalize answers, merge duplicates, dedupe clues, filter lengths."""
        max_len = max(self.width, self.height) - 1  # room for the clue block
        vocab = {}
        for raw_word, clues in word_dict.items():
            word = self.normalize_answer(raw_word)
            if not (self.min_word_len <= len(word) <= max_len):
                continue
            if isinstance(clues, str):
                clues = [clues]
            bucket = vocab.setdefault(word, [])
            for clue in clues:
                clue = clue.strip()
                if clue and clue not in bucket:
                    bucket.append(clue)
            if not bucket:
                del vocab[word]
        return vocab

    # ------------------------------------------------------------- geometry
    @staticmethod
    def _step(direction):
        return (0, 1) if direction == 'H' else (1, 0)

    @staticmethod
    def _clue_cell(row, col, direction):
        return (row, col - 1) if direction == 'H' else (row - 1, col)

    def _in_bounds(self, r, c):
        return 0 <= r < self.height and 0 <= c < self.width

    def _is_letter(self, r, c):
        return self._in_bounds(r, c) and self.grid[r][c] not in (EMPTY, BLOCK)

    # ------------------------------------------------------------ validation
    def check_placement(self, word, row, col, direction):
        """Return the number of crossings if the word fits, otherwise -1."""
        dr, dc = self._step(direction)
        end_r = row + dr * (len(word) - 1)
        end_c = col + dc * (len(word) - 1)
        clue_r, clue_c = self._clue_cell(row, col, direction)

        # 1. Word and its clue block must be inside the grid
        if not (self._in_bounds(row, col) and self._in_bounds(end_r, end_c)
                and self._in_bounds(clue_r, clue_c)):
            return -1

        # 2. Clue block: empty, or (optional) a block with a free slot
        clue_cell = self.grid[clue_r][clue_c]
        if clue_cell == BLOCK:
            if (not self.shared_clue_blocks
                    or direction in self._block_dirs[(clue_r, clue_c)]
                    or len(self._block_dirs[(clue_r, clue_c)]) >= 2):
                return -1
        elif clue_cell != EMPTY:
            return -1

        # 3. Letters: conflicts, crossings, side-by-side contact
        crossings = 0
        side_a = (-1, 0) if direction == 'H' else (0, -1)
        side_b = (1, 0) if direction == 'H' else (0, 1)
        for i, ch in enumerate(word):
            r, c = row + dr * i, col + dc * i
            cell = self.grid[r][c]
            if cell == EMPTY:
                # A new letter must not touch a letter on its sides,
                # otherwise it creates unintended 2-letter "words"
                if (self._is_letter(r + side_a[0], c + side_a[1])
                        or self._is_letter(r + side_b[0], c + side_b[1])):
                    return -1
            elif cell == ch:
                # Can only cross a word running the other way
                if direction in self._cell_dirs[(r, c)]:
                    return -1
                crossings += 1
            else:
                return -1  # different letter or a block

        # 4. Cell right after the word must not continue it
        if self._is_letter(end_r + dr, end_c + dc):
            return -1

        # 5. Don't overwrite an entire existing word with no new letters
        if crossings == len(word):
            return -1

        return crossings

    # Backwards-compatible name from the original version
    def is_valid_placement(self, word, row, col, direction):
        return self.check_placement(word, row, col, direction)

    # -------------------------------------------------------------- placing
    def place_word(self, word, clue_text, row, col, direction):
        dr, dc = self._step(direction)
        clue_r, clue_c = self._clue_cell(row, col, direction)
        self.grid[clue_r][clue_c] = BLOCK
        self._block_dirs[(clue_r, clue_c)].add(direction)

        for i, ch in enumerate(word):
            r, c = row + dr * i, col + dc * i
            self.grid[r][c] = ch
            self._cell_dirs[(r, c)].add(direction)

        self._used_words.add(word)
        self._used_clues.add(clue_text.casefold())
        self.placed_words.append({
            "word": word,
            "clue": clue_text,
            "word_start_r": row,
            "word_start_c": col,
            "direction": direction,
            "clue_box_r": clue_r,
            "clue_box_c": clue_c,
        })

    def _pick_clue(self, word, vocab):
        options = vocab[word]
        if self.unique_clues:
            options = [c for c in options if c.casefold() not in self._used_clues]
        return self.rng.choice(options) if options else None

    # ------------------------------------------------------------ generation
    def _build_letter_index(self, vocab):
        """letter -> list of (word, index of that letter in word)."""
        index = defaultdict(list)
        for word in vocab:
            for i, ch in enumerate(word):
                index[ch].append((word, i))
        return index

    def _best_candidate(self, vocab, letter_index):
        """Scan every letter on the board that still has a free direction."""
        best, best_score = None, float('-inf')
        for (r, c), dirs in list(self._cell_dirs.items()):
            letter = self.grid[r][c]
            for direction in DIRS:
                if direction in dirs:
                    continue
                for word, idx in letter_index[letter]:
                    if word in self._used_words:
                        continue
                    if (direction == 'H'):
                        row, col = r, c - idx
                    else:
                        row, col = r - idx, c
                    crossings = self.check_placement(word, row, col, direction)
                    if crossings < 1:
                        continue
                    # More crossings = denser, better puzzle; longer words
                    # fill the grid faster; random noise breaks ties.
                    score = crossings * 10 + len(word) + self.rng.random() * 3
                    if score > best_score:
                        clue = self._pick_clue(word, vocab)
                        if clue is None:
                            continue
                        best_score = score
                        best = (word, clue, row, col, direction)
        return best

    def _seed_first_word(self, vocab):
        """Place a random medium/long word somewhere near the middle."""
        words = list(vocab)
        self.rng.shuffle(words)
        words.sort(key=len, reverse=True)
        pool = words[:max(20, len(words) // 5)]  # pick among the longer words
        self.rng.shuffle(pool)
        for word in pool:
            for direction in self.rng.sample(DIRS, 2):
                if direction == 'H':
                    rows = list(range(self.height))
                    rows.sort(key=lambda r: abs(r - self.height // 2))
                    for row in rows[:3]:
                        col = self.rng.randint(1, max(1, self.width - len(word)))
                        if self.check_placement(word, row, col, 'H') != -1:
                            self.place_word(word, self._pick_clue(word, vocab), row, col, 'H')
                            return True
                else:
                    cols = list(range(self.width))
                    cols.sort(key=lambda c: abs(c - self.width // 2))
                    for col in cols[:3]:
                        row = self.rng.randint(1, max(1, self.height - len(word)))
                        if self.check_placement(word, row, col, 'V') != -1:
                            self.place_word(word, self._pick_clue(word, vocab), row, col, 'V')
                            return True
        return False

    def _single_attempt(self, vocab, letter_index):
        self._reset()
        if not self._seed_first_word(vocab):
            return False
        while True:
            candidate = self._best_candidate(vocab, letter_index)
            if candidate is None:
                return True
            self.place_word(*candidate)

    def filled_cells(self):
        return sum(cell != EMPTY for row in self.grid for cell in row)

    def generate(self, word_dict, attempts=60):
        """Try several random layouts and keep the densest one."""
        vocab = self.prepare_vocab(word_dict)
        if not vocab:
            raise ValueError("No usable words in the dictionary.")
        letter_index = self._build_letter_index(vocab)

        best_key, best_state = None, None
        for _ in range(attempts):
            if not self._single_attempt(vocab, letter_index):
                continue  # try again instead of giving up on all attempts
            key = (self.filled_cells(), len(self.placed_words))
            if best_key is None or key > best_key:
                best_key = key
                best_state = ([row[:] for row in self.grid],
                              [dict(w) for w in self.placed_words])

        if best_state is None:
            raise RuntimeError("Could not place any word - is the grid too small?")

        # Restore the best layout
        grid, words = best_state
        self._reset()
        self.grid = grid
        self.placed_words = words
        for w in words:
            self._used_words.add(w["word"])
            self._block_dirs[(w["clue_box_r"], w["clue_box_c"])].add(w["direction"])
            dr, dc = self._step(w["direction"])
            for i in range(len(w["word"])):
                self._cell_dirs[(w["word_start_r"] + dr * i,
                                 w["word_start_c"] + dc * i)].add(w["direction"])

        total = self.width * self.height
        print(f"Generation complete! Placed {len(words)} words, "
              f"{best_key[0]}/{total} cells used ({best_key[0] / total:.0%}).")
        return self

    # --------------------------------------------------------------- output
    def print_grid(self):
        border = "+" + "-" * (self.width * 2 - 1) + "+"
        print("\n" + border)
        for row in self.grid:
            print("|" + " ".join(cell if cell != EMPTY else '.' for cell in row) + "|")
        print(border)

    def to_dict(self):
        """Everything a front end needs to render the puzzle."""
        return {
            "width": self.width,
            "height": self.height,
            # one string per row; '#' = clue block, '.' = unused cell
            "grid": ["".join(cell if cell != EMPTY else '.' for cell in row)
                     for row in self.grid],
            "words": self.placed_words,
        }

    def to_json(self, **kwargs):
        kwargs.setdefault("ensure_ascii", False)  # keep 'acción', 'niño'...
        return json.dumps(self.to_dict(), **kwargs)


# --- Example Usage ---
if __name__ == "__main__":
    from vocab import VOCAB

    arroword = ArrowordGenerator(width=10, height=16)
    arroword.generate(VOCAB, attempts=60)
    arroword.print_grid()

    print("\n--- Coordinate Map & Selected Clues ---")
    print(json.dumps(arroword.placed_words, indent=2, ensure_ascii=False))
