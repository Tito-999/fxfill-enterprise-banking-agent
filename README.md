```bash
cd /mnt/f/projects/fxfill-enterprise-banking-agent

mkdir -p /tmp/fxfill-readme
unzip /path/to/fxfill-enterprise-banking-agent-readme-step1-4.zip \
  -d /tmp/fxfill-readme

cp /tmp/fxfill-readme/README.md .
cp /tmp/fxfill-readme/README.zh-CN.md .

mkdir -p docs/portfolio
cp /tmp/fxfill-readme/docs/portfolio/*.svg docs/portfolio/

git status --short
git diff --check

git add README.md README.zh-CN.md docs/portfolio
git commit -m "docs: add bilingual architecture README"
```
