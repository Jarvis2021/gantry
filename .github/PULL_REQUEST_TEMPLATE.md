## 📋 Pull Request

### Description
<!-- Describe what this PR does -->

### Type of Change
- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to change)
- [ ] 📚 Documentation update
- [ ] 🧹 Refactor (no functional changes)
- [ ] 🧪 Test update

### Checklist

#### Code Quality
- [ ] Code follows the project's style guidelines (`.cursorrules`)
- [ ] No hardcoded secrets, API keys, or credentials
- [ ] All functions have docstrings
- [ ] Complex logic has inline comments
- [ ] DRY principle followed (no duplicate code)

#### Testing
- [ ] Unit tests added/updated for new functionality
- [ ] All existing tests pass locally
- [ ] Test coverage maintained at ≥70%

#### Pydantic & Type Safety
- [ ] All data structures use Pydantic models
- [ ] Type hints added for all functions
- [ ] No `Any` types without justification

#### Security
- [ ] No sensitive data in code or logs
- [ ] Input validation implemented where needed
- [ ] Error messages don't expose internals

#### Documentation
- [ ] README updated if needed
- [ ] API changes documented
- [ ] Breaking changes noted

### Related Issues
<!-- Link any related issues: Fixes #123, Closes #456 -->

### Screenshots (if applicable)
<!-- Add screenshots for UI changes -->

---

### For Reviewers

Please verify:
1. ✅ CI pipeline passes
2. ✅ No security vulnerabilities introduced
3. ✅ Code is readable and maintainable
4. ✅ Changes align with `.cursorrules`
