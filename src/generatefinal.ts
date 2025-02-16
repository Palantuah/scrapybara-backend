import { Anthropic } from '@anthropic-ai/sdk';
import { openai as openaiClient } from '@ai-sdk/openai';
import fs from 'fs';
import path from 'path';

// Initialize both clients
const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY
});

// Use the renamed import
const openai = openaiClient;

// Define interfaces for the input data
interface NewsletterData {
  category: string;
  entries: Array<{ content: string; timestamp: string }>;
  analysis: string;
  keywords?: string[];
  lastUpdated?: string;
}

// Read all newsletter data from outputs directory
async function readNewsletterOutputs(): Promise<NewsletterData[]> {
  const outputsDir = path.join(__dirname, '..', 'outputs', 'category_reports');
  const files = fs.readdirSync(outputsDir);
  const newsletters: NewsletterData[] = [];

  for (const file of files) {
    if (file.endsWith('.json')) {
      const content = fs.readFileSync(path.join(outputsDir, file), 'utf-8');
      newsletters.push(JSON.parse(content));
    }
  }

  return newsletters;
}

// Evaluate newsletter using Claude
async function evaluateNewsletter(draft: string): Promise<string> {
  const message = await anthropic.messages.create({
    model: 'claude-3-opus-20240229',
    max_tokens: 1000,
    messages: [{
      role: 'user',
      content: `Evaluate this newsletter draft on these criteria (score each out of 10):
1. Writing Quality
2. Topic Relevance 
3. Interest Level
4. Length Appropriateness
5. Natural, human-like tone

Provide an overall score out of 100 and brief explanation for each criterion.
Finally, list 1-2 actionable suggestions for improvement.

Newsletter to evaluate:
${draft}`
    }]
  });

  return message.content[0].text;
}

// Main function to generate and evaluate newsletter
async function generateFinalNewsletter(): Promise<void> {
  try {
    const newsletters = await readNewsletterOutputs();
    
    // Generate draft using GPT-4
    const draftCompletion = await openai.chat.completions.create({
      model: 'gpt-4',
      max_tokens: 2000,
      messages: [{
        role: 'user',
        content: `Synthesize these newsletter analyses into one cohesive newsletter:
${newsletters.map(nl => `## ${nl.category}\n${nl.analysis}`).join('\n\n')}`
      }]
    });

    const finalDraft = draftCompletion.choices[0].message.content;
    
    // Evaluate using Claude
    const evaluation = await evaluateNewsletter(finalDraft);
    console.log('Evaluation:', evaluation);
    
  } catch (error) {
    console.error('Error generating final newsletter:', error);
  }
}

export { generateFinalNewsletter };
