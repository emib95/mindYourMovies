# MindYourMovies frontend

React TypeScript client for the MindYourMovies questionnaire.

## Setup

```bash
npm install
cp .env.example .env
npm run dev
```

`VITE_API_BASE_URL` should point at the FastAPI backend. It defaults to
`http://localhost:8000`.

`VITE_DONATION_URL` is optional. The app defaults to Emilio's Stripe Payment
Link; set this variable only if the support link should point somewhere else.

`VITE_CREATOR_PHOTO_URL` controls the photo in that support section. By default,
the app looks for `/emilio-banqueri.jpg`, so place that file in `public/` or set
the variable to another hosted image URL.
