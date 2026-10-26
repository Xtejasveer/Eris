# Demo slide decks

The demo decks in `templates/demo/*/` (three lectures and their three prerequisites) are built from these scripts with pptxgenjs.

To rebuild one after an edit:

    npm install pptxgenjs@3.12.0 sharp react react-dom react-icons
    node kadane.js ../kadane_max_subarray/kadane_algorithm.pptx
    node india1991.js ../india_1991_reforms/india_1991_reforms.pptx
    node projectile.js ../projectile_motion/projectile_motion.pptx
    node prereqs.js    # writes pre_kadane.pptx, pre_india.pptx and pre_physics.pptx here

Copy each prerequisite deck to its folder (kadane_prereq_arrays/arrays_running_sums.pptx,
india_1991_prereq_basics/gdp_trade_exchange_rates.pptx, projectile_prereq_vectors/vectors_sine_cosine.pptx).

Then copy the new deck into the lecture's folder in `data/` (or delete that folder and run `python main.py seed`).
Figures in the India deck are rounded World Bank, RBI and Economic Survey numbers; the sources are on each slide.
