# MindYourMovies frontend

React TypeScript client for the MindYourMovies questionnaire.

## Setup

```bash
npm install
npm run dev
```

App defaults live in `src/config.ts`:

- Local dev uses `http://localhost:8000` for the API.
- Production builds use `https://api.mindyourmovies.com`.
- Donation link and creator photo path are set there too.

Optional `VITE_*` overrides are documented in `.env.example`. You only need a
`.env` file when you want to change a default locally.

Place the creator photo at `public/emilio-banqueri.jpg`.
