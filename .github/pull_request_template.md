<!--
PR Title should follow this format:

[TA-###] <type>: Brief description

Types:
feat, fix, docs, refactor, test, chore

Example:
[TA-012] feat: Add course management API
-->

## Before You Start

- [ ] I have read and will follow the Contributing Guide.
- [ ] My branch follows the naming convention: `<type>/descriptive-name`.
- [ ] My PR title follows the required format.
- [ ] I have rebased my branch with the latest `develop`.

---

## Description

Provide a brief summary of the purpose of this pull request.

---

## Summary

- [Main change]
- [Additional change]
- [Additional change]

---

## Changes

### API

- [ ] Added endpoint(s)
- [ ] Modified endpoint(s)
- [ ] Removed endpoint(s)
- [ ] No API changes

### Database

- [ ] New migration
- [ ] Updated schema
- [ ] New model(s)
- [ ] No database changes

### Business Logic

- [ ] Added service logic
- [ ] Updated existing logic
- [ ] Refactored implementation

### AI / Background Jobs (if applicable)

- [ ] AI integration
- [ ] RAG pipeline
- [ ] Celery task
- [ ] Vector search
- [ ] Not applicable

---

## Implementation Details

Describe the implementation, important design decisions, assumptions, and any trade-offs.

---

## Why

Explain why this change is needed and how it supports the project.

---

## Breaking Changes

- [ ] No breaking changes
- [ ] This PR introduces breaking changes (describe below)

Details:

---

## Testing

### Tests Performed

- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual API testing
- [ ] Existing tests still pass

Describe what was tested.

---

## Testing Instructions

### Prerequisites

- Required environment variables
- Database migrated
- Dependencies installed

### Steps

1. Pull this branch.
2. Install dependencies.
3. Run database migrations (if applicable).
4. Start the backend server.
5. Test the affected endpoint(s).
6. Verify the expected behavior.

Expected Result:

---

## Checklist

- [ ] Code follows project conventions.
- [ ] API documentation updated (if needed).
- [ ] Database migrations included (if needed).
- [ ] Tests added or updated.
- [ ] No unnecessary files committed.
- [ ] Ready for review.