# C++ Coding Style Guide (Summary)

## 1. Naming Conventions
- **Classes/Structs**: `PascalCase` (e.g., `MyClass`)
- **Functions/Variables**: `snake_case` (e.g., `my_function`, `user_id`)
- **Constants**: `kPascalCase` with 'k' prefix (e.g., `kMaxRetryCount`)
- **Member Variables**: `snake_case_` with trailing underscore (e.g., `value_`)
- **Files**: `snake_case.cpp` / `snake_case.h`

## 2. Formatting
- **Indentation**: 2 spaces (Standard Google/LLVM style)
- **Line Length**: 80-100 characters.
- **Braces**: Open brace on the same line as `if`/`while`/`class`.
- **Spaces**: Space after `if`, `while`, `for`. No space inside parentheses.

## 3. Best Practices
- Use `#pragma once` or header guards.
- Prefer `std::unique_ptr` over raw pointers.
- Use `nullptr` instead of `NULL`.
