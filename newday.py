import pandas as pd
import time
import random
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DoctoraliaPhoneExtractor:
    def __init__(self, excel_file_path, use_proxy=False, proxy_address=None):
        """
        Initialize the extractor
        
        Args:
            excel_file_path (str): Path to the Excel file
            use_proxy (bool): Whether to use a proxy
            proxy_address (str): Proxy address in format "ip:port"
        """
        self.excel_file_path = excel_file_path
        self.use_proxy = use_proxy
        self.proxy_address = proxy_address
        self.driver = None
        
    def setup_driver(self):
        """Set up Chrome WebDriver with options"""
        chrome_options = Options()
        
        # Basic options for stability
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # User agent to appear more like a regular browser
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Proxy setup if needed
        if self.use_proxy and self.proxy_address:
            chrome_options.add_argument(f"--proxy-server={self.proxy_address}")
            logger.info(f"Using proxy: {self.proxy_address}")
        
        # Uncomment the line below to run headless (without opening browser window)
        chrome_options.add_argument("--headless")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("Chrome WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise
    
    def clean_phone(self, text):
        """
        Clean extracted text to get only the phone number and format it
        
        Args:
            text (str): Raw text containing phone number
            
        Returns:
            str: Cleaned and formatted phone number or None
        """
        # Remove non-digits
        digits = re.sub(r'\D', '', text)
        # If exactly 10 digits (Mexican phone), format as XX XXXX XXXX
        if len(digits) == 10:
            return f"{digits[:2]} {digits[2:6]} {digits[6:]}"
        return None
    
    def extract_phones(self, profile_url, row_index):
        """
        Extract up to two phone numbers from a single profile URL
        
        Args:
            profile_url (str): URL of the doctor's profile
            row_index (int): Row index for logging purposes
            
        Returns:
            list: List of up to two cleaned phone numbers
        """
        extracted_phones = []  # Use list to maintain order and allow duplicates initially
        
        try:
            logger.info(f"Processing row {row_index}: {profile_url}")
            
            # Navigate to the profile page
            self.driver.get(profile_url)
            
            # Wait for page to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Random delay to avoid being detected as a bot
            time.sleep(random.uniform(2, 4))
            
            # Find all phone containers (multiple consultorios)
            try:
                phone_containers = self.driver.find_elements(By.CSS_SELECTOR, '[data-id="gdpr-show-number-block"]')
                logger.info(f"Found {len(phone_containers)} phone containers")
                
                for container_index, phone_container in enumerate(phone_containers):
                    try:
                        # Check if we already have 2 phones
                        if len(extracted_phones) >= 2:
                            break
                            
                        # Check if full number is already visible
                        full_number_span = phone_container.find_element(By.CSS_SELECTOR, 'span[data-id="shrinked-number"]')
                        partial_number = full_number_span.text.strip()
                        
                        # If it's a partial number (contains ...), we need to click the button
                        if "..." in partial_number:
                            logger.info(f"Container {container_index + 1}: Found partial number: {partial_number}. Attempting to reveal full number.")
                            
                            # Find the "Mostrar número de teléfono" button
                            show_phone_button = phone_container.find_element(By.CSS_SELECTOR, '[data-id="show-phone-number-modal"]')
                            
                            # Get the specific modal target for this container
                            modal_target = show_phone_button.get_attribute('data-target')
                            logger.info(f"Modal target for container {container_index + 1}: {modal_target}")
                            
                            # Click the button
                            self.driver.execute_script("arguments[0].click();", show_phone_button)
                            
                            # Wait for the specific modal to appear
                            time.sleep(3)
                            
                            try:
                                # Extract the modal data-id from the target attribute
                                modal_data_id = None
                                if modal_target:
                                    # Extract data-id from target like "[data-id='address-469542-3310770736-2-phone"
                                    match = re.search(r"data-id='([^']+)", modal_target)
                                    if match:
                                        modal_data_id = match.group(1)
                                        logger.info(f"Looking for modal with data-id: {modal_data_id}")
                                
                                # Wait for the specific modal
                                if modal_data_id:
                                    modal = WebDriverWait(self.driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, f'[data-id="{modal_data_id}"]'))
                                    )
                                else:
                                    # Fallback to any visible phone modal
                                    modal = WebDriverWait(self.driver, 10).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, '.modal[data-id*="phone"].show, .modal[data-id*="phone"]:not(.fade)'))
                                    )
                                
                                logger.info(f"Modal appeared for container {container_index + 1}")
                                
                                # Wait a bit more for modal content to load
                                time.sleep(1)
                                
                                # Extract phone from this specific modal
                                phone_extracted = False
                                
                                # Primary: Find tel: links in this modal
                                tel_links = modal.find_elements(By.CSS_SELECTOR, 'a[href^="tel:"]')
                                for link in tel_links:
                                    raw_phone = link.get_attribute('href').replace('tel:', '').strip()
                                    cleaned = self.clean_phone(raw_phone)
                                    if cleaned and cleaned not in extracted_phones:
                                        extracted_phones.append(cleaned)
                                        logger.info(f"Extracted phone from tel link in container {container_index + 1}: {cleaned}")
                                        phone_extracted = True
                                        break
                                
                                # Fallback: Find bold texts in this modal
                                if not phone_extracted:
                                    bold_elements = modal.find_elements(By.CSS_SELECTOR, 'b, strong')
                                    for elem in bold_elements:
                                        raw_text = elem.text.strip()
                                        cleaned = self.clean_phone(raw_text)
                                        if cleaned and cleaned not in extracted_phones:
                                            extracted_phones.append(cleaned)
                                            logger.info(f"Extracted phone from bold text in container {container_index + 1}: {cleaned}")
                                            phone_extracted = True
                                            break
                                
                                # Last fallback: Full modal text with regex
                                if not phone_extracted:
                                    modal_text = modal.text
                                    matches = re.findall(r'\d{2}\s?\d{4}\s?\d{4}', modal_text)
                                    for match in matches:
                                        cleaned = self.clean_phone(match)
                                        if cleaned and cleaned not in extracted_phones:
                                            extracted_phones.append(cleaned)
                                            logger.info(f"Extracted phone from modal text in container {container_index + 1}: {cleaned}")
                                            phone_extracted = True
                                            break
                                
                                # Close the modal properly
                                try:
                                    close_button = modal.find_element(By.CSS_SELECTOR, '[data-dismiss="modal"], .close, button[aria-label="Close"]')
                                    self.driver.execute_script("arguments[0].click();", close_button)
                                    time.sleep(2)  # Wait for modal to close completely
                                except:
                                    # Force close modal by hiding it
                                    self.driver.execute_script("arguments[0].style.display = 'none';", modal)
                                    # Also try to remove modal backdrop
                                    try:
                                        backdrops = self.driver.find_elements(By.CSS_SELECTOR, '.modal-backdrop')
                                        for backdrop in backdrops:
                                            self.driver.execute_script("arguments[0].remove();", backdrop)
                                    except:
                                        pass
                                    time.sleep(2)
                                
                                logger.info(f"Modal closed for container {container_index + 1}")
                                
                            except TimeoutException:
                                logger.warning(f"Modal did not appear for container {container_index + 1} in row {row_index}")
                        
                        else:
                            # Full number might already be visible
                            cleaned = self.clean_phone(partial_number)
                            if cleaned and cleaned not in extracted_phones:
                                extracted_phones.append(cleaned)
                                logger.info(f"Full phone number already visible in container {container_index + 1}: {cleaned}")
                        
                        # Short delay between containers
                        time.sleep(random.uniform(2, 3))
                        
                    except NoSuchElementException as e:
                        logger.warning(f"Elements not found in container {container_index + 1} for row {row_index}: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"Error processing container {container_index + 1} for row {row_index}: {e}")
                        continue
                        
            except TimeoutException:
                logger.warning(f"No phone containers found for row {row_index}")
            except Exception as e:
                logger.warning(f"Error finding phone containers for row {row_index}: {e}")
            
            # Return list of unique phones (up to 2)
            logger.info(f"Total phones extracted for row {row_index}: {extracted_phones}")
            return extracted_phones[:2]  # Return maximum 2 phones
                
        except WebDriverException as e:
            logger.error(f"WebDriver error for row {row_index}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error for row {row_index}: {e}")
            return []
    
    def process_excel_file(self, start_row=2, max_rows=None):
        """
        Process the Excel file and extract phone numbers
        
        Args:
            start_row (int): Starting row (1-based index, default is 2 to skip header)
            max_rows (int): Maximum number of rows to process (None for all)
        """
        try:
            # Read the Excel file
            logger.info(f"Reading Excel file: {self.excel_file_path}")
            df = pd.read_excel(self.excel_file_path)
            
            if df.empty:
                logger.error("Excel file is empty")
                return
            
            # Ensure columns for Phone1 and Phone2 exist
            if 'Phone1' not in df.columns:
                df['Phone1'] = ""
            if 'Phone2' not in df.columns:
                df['Phone2'] = ""
            
            logger.info(f"Found {len(df)} rows in Excel file")
            
            # Setup WebDriver
            self.setup_driver()
            
            # Process each row
            processed_count = 0
            start_index = start_row - 1  # Convert to 0-based index
            end_index = min(len(df), start_index + max_rows) if max_rows else len(df)
            
            for index in range(start_index, end_index):
                try:
                    # Get URL from column A (index 0)
                    profile_url = df.iloc[index, 0]  # Column A
                    
                    if pd.isna(profile_url) or not profile_url:
                        logger.warning(f"No URL found in row {index + 1}")
                        df.loc[index, 'Phone1'] = "No URL"
                        continue
                    
                    # Ensure URL is properly formatted
                    if not profile_url.startswith('http'):
                        profile_url = 'https://' + profile_url.lstrip('/')
                    
                    # Extract phones
                    phones = self.extract_phones(profile_url, index + 1)
                    
                    # Update columns
                    df.loc[index, 'Phone1'] = phones[0] if phones else "No phone found"
                    df.loc[index, 'Phone2'] = phones[1] if len(phones) > 1 else ""
                    
                    processed_count += 1
                    logger.info(f"Processed {processed_count}/{end_index - start_index} profiles")
                    
                    # Save progress every 10 records
                    if processed_count % 10 == 0:
                        df.to_excel(self.excel_file_path, index=False)
                        logger.info(f"Progress saved after {processed_count} records")
                    
                    # Random delay between requests
                    time.sleep(random.uniform(3, 6))
                    
                except Exception as e:
                    logger.error(f"Error processing row {index + 1}: {e}")
                    df.loc[index, 'Phone1'] = f"Error: {str(e)}"
                    continue
            
            # Final save
            df.to_excel(self.excel_file_path, index=False)
            logger.info(f"Processing complete. Updated {processed_count} records.")
            
        except Exception as e:
            logger.error(f"Error processing Excel file: {e}")
            raise
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("WebDriver closed")

def main():
    """Main function to run the phone extractor"""
    
    # Configuration
    EXCEL_FILE_PATH = "/home/ubuntu/doctoralia-tlaxcala/doctoralia-tlaxcala.xlsx"  # Update with your Excel file path
    USE_PROXY = False  # Set to True if you need to use a Mexican proxy
    PROXY_ADDRESS = "proxy_ip:proxy_port"  # Update with actual proxy if needed
    START_ROW = 2  # Start from row 2 (assuming row 1 has headers)
    MAX_ROWS = 5000  # Process maximum 50 rows at a time (adjust as needed)
    
    # Create extractor instance
    extractor = DoctoraliaPhoneExtractor(
        excel_file_path=EXCEL_FILE_PATH,
        use_proxy=USE_PROXY,
        proxy_address=PROXY_ADDRESS if USE_PROXY else None
    )
    
    try:
        # Process the Excel file
        extractor.process_excel_file(start_row=START_ROW, max_rows=MAX_ROWS)
        print("Phone extraction completed successfully!")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        logger.error(f"Main execution error: {e}")

if __name__ == "__main__":

    main()



