import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { generateText } from 'ai';
import { openai } from '@ai-sdk/openai';
import { parse } from 'csv-parse/sync';

// Use .env.local
dotenv.config({ path: path.resolve(process.cwd(), '.env.local') });

// Validate required environment variables
const requiredEnvVars = ['OPENAI_API_KEY'];
for (const envVar of requiredEnvVars) {
  if (!process.env[envVar]) {
    throw new Error(`Missing required environment variable: ${envVar}`);
  }
}

const CSV_FILE = path.join(__dirname, '..', 'email_database.csv');
const REPORTS_DIR = path.join(__dirname, '..', 'outputs', 'category_reports');

console.log(`Reports directory: ${REPORTS_DIR}`);

// Ensure outputs directory exists
try {
  if (!fs.existsSync(REPORTS_DIR)) {
    console.log(`Creating reports directory: ${REPORTS_DIR}`);
    fs.mkdirSync(REPORTS_DIR, { recursive: true });
    console.log('Reports directory created successfully');
  } else {
    console.log('Reports directory already exists');
  }
} catch (err) {
  console.error('Error creating reports directory:', err);
  process.exit(1);
}

// Track processed Message-IDs (normalized) to avoid duplicates
const processedMessageIds = new Set<string>();

// Pointer for number of lines processed so far
let lastProcessedLine = 0;

// Buffer to store the header line
let headerLine = "";

// Cache the last CSV hash to skip unchanged processing
let lastCsvHash = "";

// Helper function for delay
function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Uses GPT-4-turbo-preview to generate a consolidated newsletter.
 * The system prompt instructs the model to preserve source details and avoid added analysis.
 */
async function generateNewsletter(category: string, content: string, existingData?: any) {
  try {
    console.log(`Generating newsletter for ${category}...`);
    // Load existing entries or start a new array
    const entries = existingData?.entries || [];

    // Split combined content into individual entries (assuming separator used in grouping)
    const newEntries = content.split('\n\n---\n\n').map(entryContent => ({
      content: entryContent.trim(),
      timestamp: new Date().toISOString()
    }));

    // Add new entries if they are not already present
    for (const newEntry of newEntries) {
      const contentExists = entries.some((entry: any) => entry.content === newEntry.content);
      if (!contentExists) {
        entries.push(newEntry);
        console.log('Added new entry for', category);
      } else {
        console.log('Skipped duplicate entry for', category);
      }
    }

    console.log(`Final entry count for ${category}: ${entries.length}`);
    // Combine entries using a separator
    const allContent = entries.map((e: any) => e.content).join('\n\n---\n\n');
    console.log(`Combined content length for ${category}: ${allContent.length}`);

    const systemPrompt = `You are a newsletter synthesizer that:
1. Preserves the original phrasing and tone from source materials.
2. Only combines what is explicitly present.
3. Uses minimal connecting language.
Do not add broader context, speculate, or change the tone.`;

    const userPrompt = `Create a consolidated ${category} newsletter that:
1. Uses the exact numbers, quotes, and details from the source materials.
2. Organizes related points together naturally.
3. Presents the information as directly as in the sources.
Do not add any extra analysis or context.

Content to synthesize:
${allContent}`;

    // Use GPT-4-turbo-preview model (higher-tier for better quality)
    const { text: generatedText } = await generateText({
      model: openai('gpt-4-turbo-preview'),
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt }
      ]
    });

    // Extract keywords using a dedicated prompt
    const keywordPrompt = `Extract the 5-7 most important topics, phrases, or themes from this content. Focus on:
1. Key events, developments, or announcements
2. Important names and organizations
3. Significant numbers or statistics
4. Recurring themes or trends
5. Notable quotes or statements

Format each as a short, clear phrase. ONLY OUTPUT SHORT PHRASES/WORDS. NO PUNCTUATION OR NON ALPHABET CHARACTERS.

Content to analyze:
${generatedText}`;

    const { text: keywordResponse } = await generateText({
      model: openai('gpt-4-turbo-preview'),
      messages: [
        { role: 'system', content: 'You are a precise topic extractor. List only the most relevant phrases, one per line.' },
        { role: 'user', content: keywordPrompt }
      ]
    });

    // Split response into individual keywords/phrases
    const keywords = keywordResponse.split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0)
      .slice(0, 7);  // Keep max 7 keywords

    return {
      entries,
      analysis: generatedText,
      keywords
    };
  } catch (error: any) {
    console.error('Error in generateNewsletter:', error);
    if (error?.lastError?.statusCode === 429) {
      console.log('Rate limit hit in generateNewsletter, waiting 20 seconds...');
      await delay(20000);
      return generateNewsletter(category, content, existingData);
    }
    throw error;
  }
}

/**
 * Loads existing JSON data for a category, generates an updated newsletter,
 * and writes the result to a file.
 */
async function updateCategoryNewsletter(category: string, content: string, existingData?: any) {
  try {
    console.log(`Updating newsletter for ${category}...`);
    const reportPath = path.join(REPORTS_DIR, `${category.toLowerCase()}.json`);
    const result = await generateNewsletter(category, content, existingData);
    fs.writeFileSync(reportPath, JSON.stringify({
      category,
      entries: result.entries,
      analysis: result.analysis,
      keywords: result.keywords,
      lastUpdated: new Date().toISOString()
    }, null, 2));
    console.log(`Updated report saved for ${category} at ${reportPath}`);
    return result;
  } catch (error) {
    console.error(`Error updating newsletter for ${category}:`, error);
    throw error;
  }
}

/**
 * Computes an MD5 hash for the given content.
 */
function computeHash(content: string): string {
  return crypto.createHash('md5').update(content.trim()).digest('hex');
}

/**
 * Polls the CSV file, groups rows by Category, and processes each group.
 */
async function processCsvFile() {
  try {
    if (!fs.existsSync(CSV_FILE)) {
      console.log('CSV file not found. Waiting for it to be created...');
      return;
    }

    const fileContent = fs.readFileSync(CSV_FILE, 'utf-8');
    console.log('Read CSV file; content length:', fileContent.length);
    const currentHash = computeHash(fileContent);
    if (currentHash === lastCsvHash) {
      console.log('CSV content unchanged. Skipping processing.');
      return;
    }
    console.log('CSV content changed, processing...');
    lastCsvHash = currentHash;

    // Parse entire CSV using csv-parse with more robust quote handling
    const records = parse(fileContent, { 
      columns: true,
      skip_empty_lines: true,
      quote: '"',
      escape: '\\',
      relax_quotes: true,
      relax_column_count: true,
      trim: true,
      ltrim: true,
      rtrim: true
    });

    // Group content by Category
    const categoryMap = new Map<string, string[]>();
    for (const record of records) {
      if (!record.Category || !record.Body || !record['Message-ID']) continue;
      // Skip if this message has been processed already
      const msgId = record['Message-ID'].trim();
      if (processedMessageIds.has(msgId)) continue;
      
      if (!categoryMap.has(record.Category)) {
        categoryMap.set(record.Category, []);
      }
      categoryMap.get(record.Category)?.push(record.Body);
      // Mark this message as processed
      processedMessageIds.add(msgId);
    }

    // Process each category (wait between categories to ease rate limiting)
    for (const [category, contents] of categoryMap) {
      console.log(`Processing category "${category}" with ${contents.length} new record(s)`);
      try {
        const reportPath = path.join(REPORTS_DIR, `${category.toLowerCase()}.json`);
        let existingData = {};
        if (fs.existsSync(reportPath)) {
          existingData = JSON.parse(fs.readFileSync(reportPath, 'utf-8'));
          console.log(`Loaded existing data for ${category}`);
        }
        const combinedContent = contents.join('\n\n---\n\n');
        await updateCategoryNewsletter(category, combinedContent, existingData);
        console.log(`Successfully updated category: ${category}`);
      } catch (error) {
        console.error(`Error processing category ${category}:`, error);
      }
      // Wait a short time between categories
      await delay(2000);
    }
  } catch (err) {
    console.error('Error processing CSV file:', err);
  }
}

// Use setInterval to poll the CSV file every 10 seconds.
setInterval(() => {
  processCsvFile().catch(err => console.error('Error during polling:', err));
}, 10000);

console.log(`Polling for changes to ${CSV_FILE} every 10 seconds...`);
