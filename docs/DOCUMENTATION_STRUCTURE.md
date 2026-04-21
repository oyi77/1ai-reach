# Documentation Structure

This document provides an overview of the 1ai-reach documentation organization.

## 📁 Root Level Documentation

### Essential Files
- **[README.md](../README.md)** - Main project overview, quick start, features
- **[EMAIL_TRACKING_COMPLETE.md](../EMAIL_TRACKING_COMPLETE.md)** - Latest feature: Email tracking implementation summary
- **[DEPLOYMENT.md](../DEPLOYMENT.md)** - Production deployment guide
- **[SKILL.md](../SKILL.md)** - AI skill definition for agent interactions
- **[CLAUDE.md](../CLAUDE.md)** - Claude AI integration notes

## 📁 docs/ Directory

### Core Documentation
- **[README.md](README.md)** - Documentation index (this file)
- **[architecture.md](architecture.md)** - Clean Architecture design and patterns
- **[data_models.md](data_models.md)** - Domain models and validation rules
- **[api_reference.md](api_reference.md)** - FastAPI endpoint documentation
- **[migration_guide.md](migration_guide.md)** - Migration from old structure

### Email Tracking Documentation
- **[EMAIL_TRACKING_COMPLETE.md](../EMAIL_TRACKING_COMPLETE.md)** - Complete implementation guide

### MCP Integration
- **[mcp-contract.md](mcp-contract.md)** - MCP server contract
- **[mcp-safety.md](mcp-safety.md)** - MCP safety guidelines

### Operations
- **[runbooks.md](runbooks.md)** - Operational procedures
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment guide

## 📊 Documentation Statistics

- **Root Level**: 5 essential files
- **docs/**: 12 active documentation files
- **docs/archive/**: 46 archived files
- **Total**: 63 documentation files

## 🔍 Finding Documentation

### By Topic

**Getting Started**
- Start with [README.md](../README.md)
- Follow [DEPLOYMENT.md](../DEPLOYMENT.md) for production setup

**Email Tracking**
- Overview: [EMAIL_TRACKING_COMPLETE.md](../EMAIL_TRACKING_COMPLETE.md)
- Setup: [BREVO_WEBHOOK_SETUP.md](BREVO_WEBHOOK_SETUP.md)
- Technical: [EMAIL_TRACKING_IMPLEMENTATION.md](EMAIL_TRACKING_IMPLEMENTATION.md)

**Architecture & Development**
- Design: [architecture.md](architecture.md)
- Models: [data_models.md](data_models.md)
- API: [api_reference.md](api_reference.md)

**Operations**
- Procedures: [runbooks.md](runbooks.md)
- MCP: [mcp-contract.md](mcp-contract.md)

### By Role

**Product Manager / Business**
- [README.md](../README.md) - Feature overview
- [EMAIL_TRACKING_COMPLETE.md](../EMAIL_TRACKING_COMPLETE.md) - Latest capabilities

**Developer**
- [architecture.md](architecture.md) - System design
- [data_models.md](data_models.md) - Data structures
- [api_reference.md](api_reference.md) - API endpoints
- [migration_guide.md](migration_guide.md) - Code migration

**DevOps / SRE**
- [DEPLOYMENT.md](../DEPLOYMENT.md) - Deployment procedures
- [runbooks.md](runbooks.md) - Operational procedures
- [BREVO_WEBHOOK_SETUP.md](BREVO_WEBHOOK_SETUP.md) - External service setup

**QA / Testing**
- [EMAIL_TRACKING_AUDIT_SUMMARY.md](EMAIL_TRACKING_AUDIT_SUMMARY.md) - Test coverage
- [EMAIL_TRACKING_IMPLEMENTATION.md](EMAIL_TRACKING_IMPLEMENTATION.md) - Testing procedures

## 📝 Documentation Standards

### File Naming
- `README.md` - Index/overview files
- `UPPERCASE.md` - Important standalone documents
- `lowercase.md` - Technical documentation
- `FEATURE_NAME_*.md` - Feature-specific docs

### Structure
- Clear headings with emoji for visual scanning
- Code examples with syntax highlighting
- Tables for structured data
- Links to related documentation

### Maintenance
- Update dates in footers
- Archive outdated documentation
- Keep README.md files current
- Link from main README to new features

## 🔄 Recent Changes

**2026-04-21**
- ✅ Consolidated email tracking documentation
- ✅ Moved 46 files to archive/
- ✅ Created docs/README.md index
- ✅ Updated main README.md with email tracking
- ✅ Organized by topic and role

## 📞 Support

For documentation issues or questions:
- Check [docs/README.md](README.md) for index
- Review [EMAIL_TRACKING_COMPLETE.md](../EMAIL_TRACKING_COMPLETE.md) for latest features
- Contact: oyi77.coder@gmail.com

---

**Last Updated**: 2026-04-21  
**Documentation Version**: 2.0  
**Project**: 1ai-reach
