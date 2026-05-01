# SOP_01_Memory_Strict

## Rule
All Python agents must explicitly import `gc` and force `gc.collect()` at the end of loop iterations to protect the 8GB RAM hardware ceiling.

## Implementation Details
- Ensure `import gc` is present in the agent's initialization or main loop module.
- Call `gc.collect()` at the end of each significant iteration or batch process.
- Monitor memory usage to ensure it stays below the 8GB threshold.
