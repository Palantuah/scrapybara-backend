import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { generateText } from 'ai';
import { openai } from '@ai-sdk/openai';
import { parse } from 'csv-parse/sync';

// Change .env to .env.local
dotenv.config({ path: path.resolve(process.cwd(), '.env.local') });

// Add validation for required environment variables
const requiredEnvVars = ['OPENAI_API_KEY'];
for (const envVar of requiredEnvVars) {
  if (!process.env[envVar]) {
    throw new Error(`Missing required environment variable: ${envVar}`);
  }
}

const CSV_FILE = path.join(__dirname, '..', 'email_database.csv');
const REPORTS_DIR = path.join(__dirname, '..', 'outputs', 'category_reports');

console.log(`Reports directory: ${REPORTS_DIR}`);

// Ensure outputs directory exists with better error handling
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
  process.exit(1);  // Exit if we can't create the directory
}

// Track processed Message-IDs to avoid duplicates (normalized)
const processedMessageIds = new Set<string>();

// Track the last processed line number (for when the CSV grows)
let lastProcessedLine = 0;

// Buffer to store header line
let headerLine = "";

// Cache the last CSV hash to avoid reprocessing unchanged data
let lastCsvHash = "";

async function generateNewsletter(category: string, content: string, existingData?: any) {
  try {
    console.log(`Generating newsletter for ${category}...`);
    console.log('Existing data:', existingData);
    
    const entries = existingData?.entries || [];
    console.log(`Current entries count: ${entries.length}`);
    
    entries.push({
      content,
      timestamp: new Date().toISOString()
    });
    console.log(`New entries count: ${entries.length}`);

    const allContent = entries.map((e: { content: string; timestamp: string }) => e.content).join('\n\n');
    console.log(`Combined content length: ${allContent.length}`);
    
    const prompt = `Create a comprehensive ${category} newsletter based on all these updates:
${allContent}

IMPORTANT: ONLY include information that is directly relevant to the ${category} category. Completely ignore any content that is not specifically about ${category}.

Create a well-structured newsletter that synthesizes all the relevant ${category} information above. Structure it with:
- Latest Developments in ${category}
- Key ${category} Trends
- ${category} Market Analysis
- Industry Insights
- Future Outlook for ${category}

Ensure all important ${category}-related information is preserved and woven together cohesively. 
DO NOT include information from other sectors or categories unless it directly impacts ${category}.`;

    console.log('Sending to OpenAI...');
    const { text } = await generateText({
      model: openai('gpt-4o-mini'),
      messages: [
        { role: 'system', content: 'You are an expert newsletter writer who creates comprehensive newsletters for users using as much of the same language and format as possible of the original documents.' },
        { role: 'user', content: prompt }
      ]
    });
    console.log('Received response from OpenAI');

    // After getting the analysis, extract keywords using GPT
    console.log('Extracting keywords from analysis...');
    const { text: keywordsText } = await generateText({
      model: openai('gpt-4o-mini'),
      messages: [
        { role: 'system', content: 'You are an expert at identifying key topics and themes.' },
        { role: 'user', content: `From the following ${category} newsletter, identify the 5-7 most important topics/keywords. 
        Format your response as a simple comma-separated list with no explanations or additional text.
        
        Newsletter:
        ${text}` }
      ]
    });

    // Clean up the keywords response
    const keywords = keywordsText
      .split(',')
      .map(k => k.trim())
      .filter(k => k.length > 0);
    
    console.log('Extracted keywords:', keywords);

    return {
      entries,
      analysis: text,
      keywords
    };
  } catch (error: any) {
    console.error('Error in generateNewsletter:', error);
    if (error?.lastError?.statusCode === 429) {
      console.log('Rate limit hit, waiting 20 seconds...');
      await new Promise(resolve => setTimeout(resolve, 20000));
      return generateNewsletter(category, content, existingData);
    }
    throw error;
  }
}

async function updateCategoryNewsletter(category: string, content: string) {
  const fileName = `${category.toLowerCase().replace(/\s+/g, '_')}.json`;
  const filePath = path.join(REPORTS_DIR, fileName);
  
  console.log(`Updating newsletter for category: ${category}`);
  console.log(`File path: ${filePath}`);
  
  let existingData = null;
  try {
    if (fs.existsSync(filePath)) {
      console.log('Found existing file, reading content...');
      existingData = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      console.log('Successfully loaded existing data');
    } else {
      console.log('No existing file found, will create new one');
    }
  } catch (err) {
    console.error(`Error reading existing newsletter for ${category}:`, err);
  }

  console.log('Generating new newsletter content...');
  const updatedData = await generateNewsletter(category, content, existingData);
  
  try {
    const fileContent = JSON.stringify({
      category,
      entries: updatedData.entries,
      analysis: updatedData.analysis,
      keywords: updatedData.keywords,
      lastUpdated: new Date().toISOString()
    }, null, 2);

    console.log(`Writing ${fileContent.length} bytes to ${filePath}`);
    fs.writeFileSync(filePath, fileContent);
    console.log(`Successfully updated ${fileName}`);
  } catch (err) {
    console.error(`Error writing newsletter file for ${category}:`, err);
    throw err;
  }
}

function computeHash(content: string): string {
  return crypto.createHash('md5').update(content.trim()).digest('hex');
}

async function processCsvFile() {
  try {
    if (!fs.existsSync(CSV_FILE)) {
      console.log('CSV file not found. Waiting for it to be created...');
      lastProcessedLine = 0;
      return;
    }

    const fileContent = fs.readFileSync(CSV_FILE, 'utf-8');
    console.log('Read CSV file, content length:', fileContent.length);

    const currentHash = computeHash(fileContent);
    if (currentHash === lastCsvHash) {
      console.log('CSV content unchanged. Skipping processing.');
      return;
    }
    console.log('CSV content changed, processing...');
    lastCsvHash = currentHash;

    const allLines = fileContent.split('\n').filter(line => line.trim().length > 0);
    console.log(`Found ${allLines.length} non-empty lines`);

    // Capture header if not yet captured
    if (lastProcessedLine === 0) {
      headerLine = allLines[0];
      lastProcessedLine = 1; // start processing after header
      console.log('Header captured:', headerLine);
    }

    if (allLines.length <= lastProcessedLine) {
      console.log('No new data beyond header. Waiting for update...');
      return;
    }

    const newLines = allLines.slice(lastProcessedLine);
    console.log(`Processing ${newLines.length} new line(s).`);

    // Prepend header to new lines to form valid CSV
    const csvToParse = [headerLine, ...newLines].join('\n');
    const records = parse(csvToParse, { 
      columns: true, 
      skip_empty_lines: true
    });

    for (const record of records) {
      if (record['Subject'] === 'Subject') continue; // skip header if parsed as record

      if (record.Category && record['Message-ID']) {
        // Clean up Message-ID by removing newlines and extra whitespace
        const msgId = record['Message-ID']
          .replace(/[\n\r]/g, '')
          .replace(/^\s+|\s+$/g, '')
          .replace(/^["']|["']$/g, '');

        if (!processedMessageIds.has(msgId)) {
          try {
            // Only process if there's actual content
            if (record.Body?.trim()) {
              console.log(`Processing message for category: ${record.Category}`);
              await updateCategoryNewsletter(record.Category, record.Body);
              console.log(`Successfully processed message: ${msgId}`);
            } else {
              console.log(`Skipping empty content for message: ${msgId}`);
            }
            processedMessageIds.add(msgId);  // Track the ID even if content was empty
          } catch (error) {
            console.error(`Error processing message ${msgId}:`, error);
          }
        } else {
          console.log(`Skipping duplicate message: ${msgId}`);
        }
      } else {
        console.log('Skipping invalid record:', record);
      }
    }

    lastProcessedLine = allLines.length;
    console.log(`Finished processing. lastProcessedLine updated to ${lastProcessedLine}.`);
  } catch (err) {
    console.error('Error processing CSV file:', err);
  }
}

// Instead of fs.watch, use setInterval to poll the CSV every 10 seconds.
setInterval(() => {
  processCsvFile().catch(err => console.error('Error during polling:', err));
}, 10000);

console.log(`Polling for changes to ${CSV_FILE} every 10 seconds...`);
