require('dotenv').config();

const fetch = require('node-fetch');
global.fetch = fetch;

const SmeeClient = require('smee-client')

const smee = new SmeeClient({
  source: process.env.SMEE_URL,
  target: 'http://127.0.0.1:3000/webhook',
  logger: console
})

const events = smee.start()
