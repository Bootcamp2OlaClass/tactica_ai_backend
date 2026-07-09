# Git Workflow & Branch Strategy

## Branches

### main

Production-ready branch.

Only stable, reviewed, and tested backend code should be merged into `main`.

---

### develop

Integration branch for ongoing backend development.

All completed features, bug fixes, and database changes should be merged into `develop` first for validation before being promoted to production.

---

### feature/*

Used for developing new backend features.

Create from `develop` and merge back into `develop` via a Pull Request.

Examples:

```
feature/auth-api
feature/course-service
feature/document-upload
```

---

### bugfix/*

Used for fixing bugs in existing backend functionality.

Create from `develop` and merge back into `develop` via a Pull Request.

Examples:

```
bugfix/fix-auth-token
bugfix/course-validation
```

---

## Workflow

1. Create a new branch from `develop`.
2. Implement the feature or bug fix.
3. Add or update tests if applicable.
4. Run local testing.
5. Commit changes following the commit convention.
6. Push the branch to GitHub.
7. Open a Pull Request targeting `develop`.
8. Complete code review and testing.
9. Merge into `develop`.
10. When `develop` is stable, open a Pull Request from `develop` to `main`.
11. Merge into `main` for production deployment.

---

## Commit Convention

```
feat: new feature
fix: bug fix
refactor: code restructuring without behavior change
docs: documentation changes
test: adding or updating tests
chore: maintenance tasks
```

Examples:

```
feat(auth): implement JWT authentication
fix(course): validate duplicate course creation
refactor(database): simplify repository layer
```

---

## Pull Request Rules

- Feature and bugfix branches must target `develop`.
- Release Pull Requests must target `main`.
- Do not push directly to `main`.
- Keep Pull Requests focused on a single feature or fix.
- Include database migrations when schema changes are introduced.
- Ensure all tests pass before requesting review.
- Update API documentation if endpoints or request/response models change.