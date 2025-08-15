import os
import json
import base64
from io import BytesIO
from typing import List, Optional
from PIL import Image
import fitz  # PyMuPDF
import logging
from datetime import datetime
from pathlib import Path

# Pydantic imports
from pydantic import BaseModel, Field, EmailStr, validator

# OpenAI client
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContactInfo(BaseModel):
    """Simple contact information model for testing"""
    name: Optional[str] = Field(None, description="Full name of the candidate")
    email: Optional[str] = Field(None, description="Email address")  # Using str instead of EmailStr for flexibility
    phone: Optional[str] = Field(None, description="Phone number")
    
    @validator('email')
    def validate_email(cls, v):
        """Basic email validation"""
        if v and '@' not in v:
            return None  # Return None if email format is invalid
        return v

class ExtractionResult(BaseModel):
    """Result of resume extraction"""
    filename: str
    success: bool
    contact_info: Optional[ContactInfo] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None
    raw_response: Optional[str] = None  # For debugging

class SimpleResumeExtractor:
    """Simple resume extractor for name, email, phone using Qwen VL"""
    
    def __init__(
        self, 
        base_url: str = "http://localhost:8000/v1",
        model_name: str = "Qwen/Qwen2-VL-7B-Instruct",
        api_key: str = "EMPTY",
        max_tokens: int = 1000,
        temperature: float = 0.1
    ):
        """
        Initialize the simple resume extractor
        
        Args:
            base_url: vLLM server base URL
            model_name: Qwen VL model name
            api_key: API key (usually "EMPTY" for local vLLM)
            max_tokens: Maximum tokens for response
            temperature: Temperature for generation
        """
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # Initialize OpenAI client for vLLM server
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )
        
        logger.info(f"Initialized SimpleResumeExtractor with model: {model_name}")

    def pdf_to_images(self, pdf_path: str, dpi: int = 200) -> List[Image.Image]:
        """Convert PDF to images"""
        try:
            doc = fitz.open(pdf_path)
            images = []
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                mat = fitz.Matrix(dpi/72, dpi/72)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                
                img_data = pix.tobytes("png")
                img = Image.open(BytesIO(img_data))
                
                # Optimize image
                img = self._optimize_image(img)
                images.append(img)
                
            doc.close()
            logger.info(f"Converted PDF to {len(images)} images")
            return images
            
        except Exception as e:
            logger.error(f"Error converting PDF: {str(e)}")
            raise

    def _optimize_image(self, image: Image.Image, max_size: int = 1344) -> Image.Image:
        """Optimize image for Qwen VL"""
        width, height = image.size
        
        if max(width, height) > max_size:
            scale_factor = max_size / max(width, height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        return image

    def image_to_base64(self, image: Image.Image) -> str:
        """Convert image to base64"""
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=95)
        return base64.b64encode(buffer.getvalue()).decode()

    def _create_extraction_prompt(self) -> str:
        """Create simple prompt for contact info extraction"""
        return """You are a resume parser. Look at this resume image and extract ONLY the candidate's contact information.

Find and extract the following information in JSON format:

{
    "name": "Full name of the person",
    "email": "Email address", 
    "phone": "Phone number"
}

Instructions:
- Extract ONLY what you can clearly see in the image
- Use null for any field you cannot find
- For name: Look for the person's full name (usually at the top)
- For email: Look for email addresses (contains @)
- For phone: Look for phone numbers (may include country codes, parentheses, dashes, etc.)
- Return ONLY valid JSON, no additional text"""

    def extract_from_image(self, image: Image.Image) -> Optional[ContactInfo]:
        """Extract contact info from single image"""
        try:
            img_base64 = self.image_to_base64(image)
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": self._create_extraction_prompt()
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            
            content = response.choices[0].message.content
            logger.debug(f"Raw model response: {content}")
            
            # Clean response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            # Parse JSON
            json_data = json.loads(content.strip())
            contact_info = ContactInfo(**json_data)
            
            logger.info("Successfully extracted contact information")
            return contact_info
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            logger.error(f"Raw content: {content}")
            return None
        except Exception as e:
            logger.error(f"Error extracting from image: {str(e)}")
            return None

    def merge_contact_info(self, contact_list: List[ContactInfo]) -> ContactInfo:
        """Merge contact info from multiple pages"""
        if not contact_list:
            return ContactInfo()
        
        if len(contact_list) == 1:
            return contact_list[0]
        
        # Use first non-null value for each field
        merged = ContactInfo()
        
        for contact in contact_list:
            if not merged.name and contact.name:
                merged.name = contact.name
            if not merged.email and contact.email:
                merged.email = contact.email
            if not merged.phone and contact.phone:
                merged.phone = contact.phone
        
        return merged

    def extract_from_pdf(self, pdf_path: str) -> ExtractionResult:
        """Extract contact info from PDF"""
        start_time = datetime.now()
        filename = Path(pdf_path).name
        
        try:
            logger.info(f"Processing: {filename}")
            
            # Convert PDF to images
            images = self.pdf_to_images(pdf_path)
            
            # Extract from each page
            contact_list = []
            raw_responses = []
            
            for i, image in enumerate(images):
                logger.info(f"Processing page {i+1}/{len(images)}")
                contact_info = self.extract_from_image(image)
                if contact_info:
                    contact_list.append(contact_info)
            
            if not contact_list:
                return ExtractionResult(
                    filename=filename,
                    success=False,
                    error="No contact information found",
                    processing_time=(datetime.now() - start_time).total_seconds()
                )
            
            # Merge contact info from all pages
            merged_contact = self.merge_contact_info(contact_list)
            processing_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Successfully processed {filename} in {processing_time:.2f}s")
            
            return ExtractionResult(
                filename=filename,
                success=True,
                contact_info=merged_contact,
                processing_time=processing_time
            )
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Error processing {filename}: {str(e)}")
            
            return ExtractionResult(
                filename=filename,
                success=False,
                error=str(e),
                processing_time=processing_time
            )

    def batch_process(self, pdf_directory: str, output_file: Optional[str] = None) -> List[ExtractionResult]:
        """Process multiple PDFs"""
        pdf_dir = Path(pdf_directory)
        pdf_files = list(pdf_dir.glob("*.pdf"))
        
        if not pdf_files:
            logger.warning(f"No PDF files found in {pdf_directory}")
            return []
        
        logger.info(f"Found {len(pdf_files)} PDF files")
        
        results = []
        for pdf_file in pdf_files:
            try:
                result = self.extract_from_pdf(str(pdf_file))
                results.append(result)
                
                if result.success:
                    contact = result.contact_info
                    logger.info(f"✓ {result.filename}: {contact.name} | {contact.email} | {contact.phone}")
                else:
                    logger.error(f"✗ {result.filename}: {result.error}")
                    
            except Exception as e:
                logger.error(f"✗ Error with {pdf_file.name}: {str(e)}")
                results.append(ExtractionResult(
                    filename=pdf_file.name,
                    success=False,
                    error=str(e)
                ))
        
        # Save results
        if output_file:
            self._save_results(results, output_file)
        
        # Summary
        successful = sum(1 for r in results if r.success)
        logger.info(f"Complete: {successful}/{len(results)} successful")
        
        return results

    def _save_results(self, results: List[ExtractionResult], output_file: str):
        """Save results to JSON"""
        try:
            json_data = []
            for result in results:
                result_dict = {
                    "filename": result.filename,
                    "success": result.success,
                    "processing_time": result.processing_time,
                    "error": result.error
                }
                
                if result.contact_info:
                    result_dict["contact_info"] = {
                        "name": result.contact_info.name,
                        "email": result.contact_info.email,
                        "phone": result.contact_info.phone
                    }
                
                json_data.append(result_dict)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Results saved to {output_file}")
            
        except Exception as e:
            logger.error(f"Error saving results: {str(e)}")

def main():
    """Simple test example"""
    
    # Initialize extractor
    extractor = SimpleResumeExtractor(
        base_url="http://localhost:8000/v1",
        model_name="Qwen/Qwen2-VL-7B-Instruct",
        max_tokens=500,  # Reduced since we only need basic info
        temperature=0.1
    )
    
    print("=== Simple Resume Contact Extraction Test ===\n")
    
    # Test single file
    if os.path.exists("test_resume.pdf"):
        print("Testing single PDF...")
        result = extractor.extract_from_pdf("test_resume.pdf")
        
        if result.success:
            contact = result.contact_info
            print(f"✓ Success!")
            print(f"  Name: {contact.name}")
            print(f"  Email: {contact.email}")
            print(f"  Phone: {contact.phone}")
            print(f"  Processing time: {result.processing_time:.2f}s")
        else:
            print(f"✗ Failed: {result.error}")
    
    # Test batch processing
    if os.path.exists("./test_resumes"):
        print("\nTesting batch processing...")
        results = extractor.batch_process(
            pdf_directory="./test_resumes",
            output_file="contact_extraction_results.json"
        )
        
        print(f"\nResults Summary:")
        for result in results:
            if result.success:
                contact = result.contact_info
                print(f"  {result.filename}:")
                print(f"    Name: {contact.name or 'Not found'}")
                print(f"    Email: {contact.email or 'Not found'}")
                print(f"    Phone: {contact.phone or 'Not found'}")
            else:
                print(f"  {result.filename}: FAILED - {result.error}")

if __name__ == "__main__":
    main()
