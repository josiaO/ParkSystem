# Zirp documentation site

A single page with the download link and a short version of every guide. Open
`index.html` in a browser; there's no build step.

| File | What it is |
|---|---|
| `index.html` | The page |
| `styles.css` | Light and dark themes |
| `app.js` | Theme switch, sidebar highlighting, and the download card |

The download card shows the version written into the page. When the browser is
online, it fetches the newest release from GitHub and updates the version,
size, link and SHA-256 itself, so you don't have to edit the page for every
release. Pre-releases count.

The full guides live in [`../docs`](../docs/README.md); the page links to them
on GitHub. Images come from `../docs/images` and `../app/assets`, so keep the
folder inside the repository when you open it.
