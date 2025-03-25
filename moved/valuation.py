import ollama
import re

def evaluate_answer(question, answer, max_score):
    prompt = f"{answer} this is an answer written by a student for the question '{question}'. how much marks will you give out of {max_score}? say only the marks don't explain anything else."
    
    for _ in range(3):  # Try 3 times if AI doesn't return a valid number
        response = ollama.chat(model="mistral:latest", messages=[{"role": "user", "content": prompt}])
        response_text = response['message']['content'].strip()

        print(f"\n****************************************************************\nAI response: {response_text}")
        
        # Extract numerical value from response
        match = re.search(r'\d+', response_text)
        if match:
            score = int(match.group())
            if score <= max_score:
                print(f"Score: {score}")
                return score
            continue
        print("AI failed to provide a valid score. Trying again...")
    
    return -1  # Return -1 if AI fails after 3 attempts