# retry-utils

A small retry helper for flaky HTTP calls. Published on npm.

## Install

```bash
npm install @octo-org/retry-utils
```

Or from source:

```bash
git clone git@github.com:octo-org/retry-utils.git
cd retry-utils && npm install
```

## Usage

```js
import { withRetry } from '@octo-org/retry-utils'

const data = await withRetry(() => fetch('https://api.example.com/orders'), {
  attempts: 3,
  backoffMs: 200,
})
```

## Why not just use axios-retry

`axios-retry` couples you to axios. This works with any promise-returning
function, including the native `fetch` in Cloudflare Workers, where the axios
Node adapter is unavailable.

## Development

Tests run with vitest:

```bash
npm test
```

To debug a single test locally I usually run:

```bash
cd /Users/mchen/code/retry-utils && npx vitest run test/backoff.test.ts
```

## License

MIT
