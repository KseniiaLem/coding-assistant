---
name: architecture-design
description: Load this skill before designing or implementing any feature that spans multiple files, functions, or components.
---

Follow this process strictly, in order:

1. **Explore first.** Use search_files and read_file to understand what
   already exists. Never design in ignorance of the current structure.
2. **Design before code.** Present a short design containing:
   - components and the single responsibility of each;
   - data flow between components (what calls what, what data moves);
   - planned file structure (one module = one responsibility);
   - external dependencies, only if truly required.
3. **Stop and wait.** Ask the user to approve or adjust the design.
   Do not create any files before approval.
4. **Implement minimally.** Build exactly what was approved, nothing
   extra. Prefer the standard library.
5. **Summarize.** After implementation, list the files created and how
   they map to the approved design.

Design rules:
* Separate concerns: logic, interface, and data access live in
  different modules.
* Dependencies point one way: interface depends on logic, logic
  depends on data access - never the reverse.
* If a component needs more than one sentence to describe its
  responsibility, split it.
