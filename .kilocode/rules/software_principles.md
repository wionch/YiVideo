# Software Engineering Principles

Follow these core principles for all code implementations:

## KISS Principle (Keep It Simple, Stupid)

-   Write simple, straightforward code that is easy to understand
-   Avoid unnecessary complexity and over-engineering
-   Prefer clear, explicit implementations over clever tricks
-   If a solution seems too complex, look for a simpler approach
-   Maximum function length: 50 lines (unless absolutely necessary)

## DRY Principle (Don't Repeat Yourself)

-   Never duplicate code - extract repeated logic into reusable functions
-   Create helper functions or utility modules for common operations
-   If you see the same pattern 3+ times, refactor it
-   Each piece of knowledge should have a single, authoritative representation
-   When fixing bugs, ensure the fix applies to all instances

## YAGNI Principle (You Aren't Gonna Need It)

-   Only implement features that are currently required
-   Do not add functionality based on speculation about future needs
-   Avoid creating abstractions until they are actually needed
-   Remove unused code, functions, and imports
-   Focus on solving the current problem, not hypothetical future problems

## SOLID Principles

### Single Responsibility Principle (SRP)

-   Each class/module/function should have one clear responsibility
-   If describing the purpose requires "and", it likely needs splitting
-   Changes to requirements should only affect one module

### Open/Closed Principle (OCP)

-   Design for extension without modification
-   Use interfaces, abstract classes, and composition
-   New features should be added through extension, not by changing existing code

### Liskov Substitution Principle (LSP)

-   Subtypes must be substitutable for their base types
-   Derived classes should extend, not replace, base class behavior
-   Maintain the contract established by parent classes

### Interface Segregation Principle (ISP)

-   Prefer multiple specific interfaces over one general-purpose interface
-   Clients should not depend on methods they don't use
-   Keep interfaces focused and minimal

### Dependency Inversion Principle (DIP)

-   Depend on abstractions, not concrete implementations
-   High-level modules should not depend on low-level modules
-   Both should depend on abstractions

## Code Review Checklist

Before submitting code, verify:

-   [ ] Is the solution as simple as possible? (KISS)
-   [ ] Is there any duplicated code? (DRY)
-   [ ] Did I add features not in the requirements? (YAGNI)
-   [ ] Does each class/function have a single, clear purpose? (SRP)
-   [ ] Can I extend functionality without modifying existing code? (OCP)
-   [ ] Are all dependencies on abstractions rather than concrete types? (DIP)
