import os
os.environ["OPENAI_API_KEY"] = "REPLACE_WITH_YOUR_KEY"

def compose_prompt(base_prompt, additional_text):
    return base_prompt + "\n" + additional_text

from openai import OpenAI

client = OpenAI()


def generate_text(prompt, model="gpt-3.5-turbo", max_tokens=500, temperature=0.7):
    response = client.chat.completions.create(
      model=model,
      messages=[ {"role": "user", "content": prompt} ],
      max_tokens=max_tokens,
      temperature=temperature
    )
    return response.choices[0].message


# Example usage:
base_prompt = """Act as a expert DevOps engineer, generate a dockerfile. \n"""
additional_text = "Build a httpd image from ubuntu base image"
composed_prompt = compose_prompt(base_prompt, additional_text)
generated_story = generate_text(composed_prompt)
print(generated_story)

def generate_template(template, placeholders):
    filled_prompt = template.format(**placeholders)
    return generate_text(filled_prompt)

# Example usage:
template = "Write an email to {receiver}. I want to {action}."
placeholders = {'receiver': 'hr@mycompany.com', 'action': 'take a sick leave for 3 days'}
generated_story = generate_template(template, placeholders)
print(generated_story)

placeholders = {'receiver': 'projectlead@mycompany.com', 'action': 'I want to get 100 percent hike for my excellent work'}
generated_story = generate_template(template, placeholders)
print(generated_story)


# Example usage:
buggy_code = """
def greatestOf3Numbers(a,b):
  return a if a>b else b
"""

template = "Act as a expert programmer in {programming_lang}. Fix the bug in the code {my_code}."
placeholders = {'programming_lang': 'Python', 'my_code': buggy_code}
generated_story = generate_template(template, placeholders)

print(generated_story)

