# shared by the attack scripts: copies a correct reference build (kept outside the repo, never committed)
REF=/tmp/claude-0/-home-user/d0ed3385-ed4c-537c-b3f9-34da721ed499/scratchpad/ref
ref() { for f in "$@"; do mkdir -p "$(dirname "$f")"; cp "$REF/$f" "$f"; done; }
