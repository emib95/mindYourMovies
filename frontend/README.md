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

`VITE_DONATION_URL` is optional. Set it to a Stripe Payment Link URL to enable
the "Buy me a coffee" support link near the end of the app.

`VITE_CREATOR_PHOTO_URL` controls the photo in that support section. By default,
the app looks for `/emilio-banqueri.jpg`, so place that file in `public/` or set
the variable to another hosted image URL.
