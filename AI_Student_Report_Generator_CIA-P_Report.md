# AI Student Report Generator

**CIA-P (BTIN337) | Gen AI Applications**

## 1. Abstract

AI Student Report Generator is a generative AI application intended to help students prepare clear, well-structured academic reports from project details they provide. The user supplies information such as the project title, objectives, methods, tools and outcomes. Gemini generates an organized draft that the student can review and refine. The application supports report preparation while leaving fact checking and final authorship with the student.

## 2. Methodology

The workflow collects the student's project information, checks that required inputs are present, and sends the prompt to Gemini with instructions to produce concise, section-based academic writing. The generated draft is returned for review and editing. The application is designed to keep API credentials in environment variables, validate requests, and show a useful message if generation fails. The student verifies the output against the actual project before using it.

## 3. API Discussion

The application uses the Gemini API for report generation. A request contains the student's project details and generation instructions; the response contains the generated text, which is presented as a draft. An application API can expose report generation to other clients through a documented JSON endpoint. Requests should be validated and authenticated with an API key, and responses should use appropriate HTTP status codes. Webhooks can notify a registered client when report generation is complete, using JSON payloads. These integration features should be described as implemented only if they are present in the submitted application.

## 4. Safety Utilised

The Gemini key is stored outside the source code in an environment variable. Input validation and request timeouts help manage invalid or stalled requests, while error handling covers API and network failures. Students should avoid entering sensitive personal information, verify facts and citations, and edit generated text to reflect their own work. The generated report is an aid and may contain inaccurate or incomplete content.

## 5. Conclusion and Future Scope

The project applies generative AI to a practical academic writing task by turning project notes into an editable report draft. Future improvements include adding report templates, export to DOCX or PDF, saved drafts, stronger authentication and rate limiting, and tested webhook notifications. Further refinement can improve factual checks and allow students to tailor tone and section structure to their institution's format.
