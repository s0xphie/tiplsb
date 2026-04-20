import numpy as np
import pygame
import sys
import time
import subprocess

# Parameters
GRID_SIZE = 189  # x and y size
CELL_SIZE = 1   # Each cell is a single pixel
FPS = 240  # Even faster processing

# Colors for sandpile heights
COLORS = [
    (64, 64, 64),     # #404040 (0)
    (113, 113, 113),  # #717171 (1)
    (166, 166, 166),  # #a6a6a6 (2)
    (201, 201, 201),  # #c9c9c9 (3)
]

from collections import deque
def topple_2d(grid):
    # Optimized sandpile toppling using a queue of active cells
    active = deque()
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            if grid[y, x] >= 4:
                active.append((y, x))
    while active:
        y, x = active.popleft()
        while grid[y, x] >= 4:
            grid[y, x] -= 4
            for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                nx, ny = x+dx, y+dy
                if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                    grid[ny, nx] += 1
                    if grid[ny, nx] == 4:
                        active.append((ny, nx))
    return grid


def main(image_file):
    # Visualization setup
    pygame.init()
    screen = pygame.display.set_mode((GRID_SIZE*CELL_SIZE, GRID_SIZE*CELL_SIZE))
    pygame.display.set_caption('ASM: x/y sandpile, z input stream (cumulative)')
    clock = pygame.time.Clock()
    center_row = GRID_SIZE // 2
    grid2d = np.zeros((GRID_SIZE, GRID_SIZE), dtype=int)

    # Background cycling setup
    # Cycle background: start with violet, then orange, blue, yellow
    bg_palette = [COLORS[0], COLORS[1], COLORS[2], COLORS[3]]
    bg_index = 0
    # Ensure the first frame background is violet
    screen.fill(bg_palette[bg_index])
    pygame.display.flip()
    # Stream tape snapshots from asmlsb.py as a subprocess
    proc = subprocess.Popen([
        sys.executable, 'asmlsb.py', image_file
    ], stdout=subprocess.PIPE, text=True, bufsize=1)
    try:
        first_frame = True
        for line in proc.stdout:
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("("):
                continue
            # Parse a row of 17 space-separated integers
            try:
                heights = [int(x) for x in line.split()]
            except Exception:
                continue
            if len(heights) != 17:
                continue
            # Center injection: middle cell of tape at grid center
            center_col = GRID_SIZE // 2
            tape_center = len(heights) // 2
            start_col = center_col - tape_center
            for i, val in enumerate(heights):
                grid_col = start_col + i
                if 0 <= grid_col < GRID_SIZE:
                    grid2d[center_row, grid_col] += val
            # Topple in x/y until stable
            grid2d = topple_2d(grid2d)
            # Visualize current grid
            if first_frame:
                # Already filled with violet, don't cycle yet
                first_frame = False
            else:
                screen.fill(bg_palette[bg_index])
            for y in range(GRID_SIZE):
                for x in range(GRID_SIZE):
                    h = grid2d[y,x] % 4
                    color = COLORS[h]
                    rect = pygame.Rect(x*CELL_SIZE, y*CELL_SIZE, CELL_SIZE, CELL_SIZE)
                    pygame.draw.rect(screen, color, rect)
            pygame.display.flip()
            # Cycle background color after first frame
            if not first_frame:
                bg_index = (bg_index + 1) % len(bg_palette)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    proc.terminate()
                    pygame.quit()
                    sys.exit(0)
            clock.tick(FPS)
    finally:
        proc.terminate()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 asm3d.py <image_file>")
        sys.exit(1)
    main(sys.argv[1])
