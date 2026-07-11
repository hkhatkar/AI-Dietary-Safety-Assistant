# Frontend

React + Vite + TypeScript UI for Can I Eat This? — see the [root README](../README.md) for what
this project is and how to run the whole thing. Also deployed as a static site on S3 +
CloudFront (see [infra/README.md](../infra/README.md)) - no server needed to view it, just a
build step.

```bash
npm install
npm run dev
```

Needs a backend to talk to (either the live deployed one, or run your own — see
[backend/README.md](../backend/README.md)) and `VITE_API_BASE_URL` set in the repo-root `.env`
(defaults to `http://localhost:8000`).
