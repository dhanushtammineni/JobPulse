import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
after(() => server.close())
const { default: Card } = await server.ssrLoadModule('/src/components/JobCard.jsx')
const { default: Details } = await server.ssrLoadModule('/src/components/JobDetails.jsx')
const { fetchJobs } = await server.ssrLoadModule('/src/services/api.js')

test('all sources show attribution, nullable dates, and safe external application links', () => {
  for (const source of ['python.org', 'greenhouse', 'lever', 'ashby']) {
    const job = { source, source_board: 'acme', title: 'Engineer', company: 'Acme',
      url: 'https://example.test/job', apply_url: 'https://example.test/apply', description: '<script>alert(1)</script>' }
    const card = renderToStaticMarkup(React.createElement(Card, { job }))
    assert.match(card, new RegExp(source))
    assert.match(card, /Date unavailable/)
    const details = renderToStaticMarkup(React.createElement(Details, { job }))
    assert.match(details, /href="https:\/\/example.test\/apply"/)
    assert.match(details, /noopener noreferrer/)
    assert.ok(!details.includes('<script>'))
    assert.match(details, /Compensation unavailable/)
  }
})

test('source, keyword, workplace and pagination are sent to FastAPI', async () => {
  const original = globalThis.fetch
  let requested
  globalThis.fetch = async (url) => { requested = url; return { ok: true, json: async () => ({ items: [], total: 0 }) } }
  try {
    assert.deepEqual(await fetchJobs({ source: 'lever', keyword: 'Python', workplace_type: 'hybrid' }, { page: 2, pageSize: 6 }), { items: [], total: 0 })
    const params = new URL(requested, 'https://example.test').searchParams
    assert.equal(params.get('source'), 'lever')
    assert.equal(params.get('page'), '2')
    assert.equal(params.get('page_size'), '6')
    assert.equal(params.get('keyword'), 'Python')
    assert.equal(params.get('workplace_type'), 'hybrid')
  } finally { globalThis.fetch = original }
})
