#!/usr/bin/env python3
"""
REI Provider Scraper - Real Implementation
Uses Playwright to scrape Healthgrades and Cigna
"""

import asyncio
from playwright.async_api import async_playwright, Page, Browser
from dataclasses import dataclass
from typing import List, Optional, Dict
import re
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Provider:
    name: str
    clinic: Optional[str]
    address: str
    city: str
    state: str
    zip_code: str
    phone: Optional[str]
    specialties: List[str]
    healthgrades_score: Optional[float]
    review_count: Optional[int]
    cigna_in_network: Optional[bool]
    cigna_plans: List[str]
    source: str
    profile_url: Optional[str] = None
    
    def to_dict(self):
        return {
            'name': self.name,
            'clinic': self.clinic,
            'address': self.address,
            'city': self.city,
            'state': self.state,
            'zip_code': self.zip_code,
            'phone': self.phone,
            'specialties': self.specialties,
            'healthgrades_score': self.healthgrades_score,
            'review_count': self.review_count,
            'cigna_in_network': self.cigna_in_network,
            'cigna_plans': self.cigna_plans,
            'source': self.source,
            'profile_url': self.profile_url
        }


class HealthgradesScraper:
    """Scraper for Healthgrades.com REI providers"""
    
    BASE_URL = "https://www.healthgrades.com"
    
    def __init__(self, headless: bool = True, delay: float = 2.0):
        self.headless = headless
        self.delay = delay
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.page = await self.browser.new_page()
        await self.page.set_viewport_size({'width': 1920, 'height': 1080})
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def search_providers(self, state: str, max_results: int = 50) -> List[Provider]:
        """
        Search for REI providers in a state
        
        Args:
            state: Two-letter state code (e.g., 'CA', 'NY')
            max_results: Maximum number of providers to return
        """
        providers = []
        
        try:
            # Build search URL for Reproductive Endocrinology
            search_term = "reproductive endocrinology"
            search_url = f"{self.BASE_URL}/usearch?what={search_term.replace(' ', '%20')}&where={state}"
            
            logger.info(f"Navigating to: {search_url}")
            await self.page.goto(search_url, wait_until='networkidle')
            await asyncio.sleep(self.delay)
            
            # Handle any popups/cookies
            await self._handle_popups()
            
            # Get all provider cards on the page
            page_num = 1
            while len(providers) < max_results:
                logger.info(f"Scraping page {page_num}, found {len(providers)} providers so far")
                
                # Extract providers from current page
                page_providers = await self._extract_providers_from_page(state)
                providers.extend(page_providers)
                
                if len(providers) >= max_results:
                    break
                
                # Check for next page
                has_next = await self._go_to_next_page()
                if not has_next:
                    logger.info("No more pages")
                    break
                
                page_num += 1
                await asyncio.sleep(self.delay)
            
            logger.info(f"Total providers found: {len(providers)}")
            return providers[:max_results]
            
        except Exception as e:
            logger.error(f"Error searching providers: {e}")
            return providers
    
    async def _handle_popups(self):
        """Handle cookie consent and other popups"""
        try:
            # Accept cookies if present
            cookie_button = await self.page.query_selector('button:has-text("Accept")')
            if cookie_button:
                await cookie_button.click()
                await asyncio.sleep(0.5)
            
            # Close any modals
            close_buttons = await self.page.query_selector_all('[aria-label="Close"], .close, .modal-close')
            for btn in close_buttons:
                try:
                    await btn.click()
                    await asyncio.sleep(0.3)
                except:
                    pass
        except Exception as e:
            logger.debug(f"Popup handling error (non-critical): {e}")
    
    async def _extract_providers_from_page(self, state: str) -> List[Provider]:
        """Extract provider data from current page"""
        providers = []
        
        try:
            # Wait for provider cards to load
            await self.page.wait_for_selector('[data-testid="provider-card"], .provider-card, .search-result', timeout=10000)
            
            # Get all provider cards
            cards = await self.page.query_selector_all('[data-testid="provider-card"], .provider-card, .search-result, article')
            
            for card in cards:
                try:
                    provider = await self._parse_provider_card(card, state)
                    if provider:
                        providers.append(provider)
                except Exception as e:
                    logger.debug(f"Error parsing card: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error extracting providers from page: {e}")
        
        return providers
    
    async def _parse_provider_card(self, card, state: str) -> Optional[Provider]:
        """Parse a single provider card"""
        try:
            # Extract name
            name_elem = await card.query_selector('h3, .provider-name, [data-testid="provider-name"]')
            name = await name_elem.inner_text() if name_elem else "Unknown"
            name = name.strip()
            
            # Extract profile URL
            link_elem = await card.query_selector('a[href*="/physician/"]')
            profile_url = None
            if link_elem:
                href = await link_elem.get_attribute('href')
                if href:
                    profile_url = f"{self.BASE_URL}{href}" if href.startswith('/') else href
            
            # Extract clinic/practice name
            clinic_elem = await card.query_selector('.practice-name, .clinic-name, [data-testid="practice-name"]')
            clinic = await clinic_elem.inner_text() if clinic_elem else None
            if clinic:
                clinic = clinic.strip()
            
            # Extract location
            location_elem = await card.query_selector('.location, address, [data-testid="location"]')
            location_text = await location_elem.inner_text() if location_elem else ""
            
            # Parse address components
            city, zip_code, address = self._parse_location(location_text, state)
            
            # Extract phone
            phone_elem = await card.query_selector('.phone, [data-testid="phone"]')
            phone = await phone_elem.inner_text() if phone_elem else None
            if phone:
                phone = phone.strip()
            
            # Extract rating/score
            score = None
            review_count = None
            
            # Try multiple selectors for rating
            rating_elem = await card.query_selector('.rating, .score, [data-testid="rating"]')
            if rating_elem:
                rating_text = await rating_elem.inner_text()
                # Extract number from text like "4.5" or "4.5 out of 5"
                score_match = re.search(r'(\d+\.?\d*)', rating_text)
                if score_match:
                    score = float(score_match.group(1))
            
            # Try to get review count
            review_elem = await card.query_selector('.review-count, [data-testid="review-count"]')
            if review_elem:
                review_text = await review_elem.inner_text()
                review_match = re.search(r'(\d+)', review_text.replace(',', ''))
                if review_match:
                    review_count = int(review_match.group(1))
            
            # Extract specialties
            specialties = ["Reproductive Endocrinology", "Infertility"]
            specialty_elem = await card.query_selector('.specialty, .specialties')
            if specialty_elem:
                spec_text = await specialty_elem.inner_text()
                if spec_text:
                    specialties = [s.strip() for s in spec_text.split(',')]
            
            return Provider(
                name=name,
                clinic=clinic,
                address=address or location_text.strip(),
                city=city,
                state=state,
                zip_code=zip_code,
                phone=phone,
                specialties=specialties,
                healthgrades_score=score,
                review_count=review_count,
                cigna_in_network=None,  # Will be filled by Cigna scraper
                cigna_plans=[],
                source='healthgrades',
                profile_url=profile_url
            )
            
        except Exception as e:
            logger.debug(f"Error parsing provider card: {e}")
            return None
    
    def _parse_location(self, location_text: str, state: str) -> tuple:
        """Parse city, zip, and address from location text"""
        city = ""
        zip_code = ""
        address = location_text.strip()
        
        try:
            # Common patterns:
            # "123 Main St, Los Angeles, CA 90210"
            # "Los Angeles, CA 90210"
            
            # Remove state abbreviation
            text_no_state = re.sub(rf',?\s*{state}\s*', ', ', location_text, flags=re.IGNORECASE)
            
            # Try to extract ZIP
            zip_match = re.search(r'(\d{5}(-\d{4})?)', text_no_state)
            if zip_match:
                zip_code = zip_match.group(1)
                text_no_zip = text_no_state.replace(zip_code, '').strip(', ')
            else:
                text_no_zip = text_no_state
            
            # Split by commas
            parts = [p.strip() for p in text_no_zip.split(',') if p.strip()]
            
            if len(parts) >= 2:
                # Last part before state is usually city
                city = parts[-1]
                # Everything before city is address
                address = ', '.join(parts[:-1])
            elif len(parts) == 1:
                city = parts[0]
            
        except Exception as e:
            logger.debug(f"Error parsing location: {e}")
        
        return city, zip_code, address
    
    async def _go_to_next_page(self) -> bool:
        """Navigate to next page of results"""
        try:
            # Look for next page button
            next_button = await self.page.query_selector('a[aria-label="Next"], .pagination-next, button:has-text("Next")')
            
            if next_button:
                # Check if disabled
                disabled = await next_button.get_attribute('disabled')
                if disabled:
                    return False
                
                await next_button.click()
                await self.page.wait_for_load_state('networkidle')
                await asyncio.sleep(self.delay)
                return True
            
            # Try page number links
            current_page = await self.page.query_selector('.pagination .active, .page-active')
            if current_page:
                current_num = await current_page.inner_text()
                try:
                    next_num = int(current_num) + 1
                    next_page_link = await self.page.query_selector(f'a:has-text("{next_num}")')
                    if next_page_link:
                        await next_page_link.click()
                        await self.page.wait_for_load_state('networkidle')
                        await asyncio.sleep(self.delay)
                        return True
                except:
                    pass
            
            return False
            
        except Exception as e:
            logger.debug(f"Error going to next page: {e}")
            return False


class CignaScraper:
    """Scraper for Cigna provider directory"""
    
    BASE_URL = "https://www.cigna.com"
    
    def __init__(self, headless: bool = True, delay: float = 2.0):
        self.headless = headless
        self.delay = delay
    
    async def check_provider(self, provider: Provider) -> Dict:
        """
        Check if a provider is in Cigna network
        
        Args:
            provider: Provider object with name and location
            
        Returns:
            Dict with 'in_network' (bool) and 'plans' (list)
        """
        # Placeholder - implement actual Cigna scraping
        # This would search Cigna's provider directory
        await asyncio.sleep(self.delay)
        return {
            'in_network': None,
            'plans': []
        }


class REIScraper:
    """Main scraper that combines multiple sources"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
    
    async def scrape(self, state: str, sources: List[str] = None, 
                     network: Optional[str] = None, max_results: int = 50) -> List[Provider]:
        """
        Scrape REI providers from multiple sources
        
        Args:
            state: US state abbreviation
            sources: List of sources ['healthgrades', 'cigna']
            network: Filter by network ('cigna' or None)
            max_results: Maximum providers to return
        """
        if sources is None:
            sources = ['healthgrades']
        
        providers = []
        
        if 'healthgrades' in sources:
            logger.info(f"Scraping Healthgrades for {state}...")
            async with HealthgradesScraper(headless=self.headless) as hg:
                hg_providers = await hg.search_providers(state, max_results)
                providers.extend(hg_providers)
                logger.info(f"Found {len(hg_providers)} providers on Healthgrades")
        
        # TODO: Add Cigna integration
        if 'cigna' in sources:
            logger.info("Cigna integration not yet implemented")
        
        # Filter by network if specified
        if network == 'cigna':
            # Would need to check each provider against Cigna
            pass
        
        return providers


# Synchronous wrapper for Flask
def scrape_providers(state: str, sources: List[str] = None, 
                     network: Optional[str] = None, max_results: int = 50) -> List[Provider]:
    """Synchronous wrapper for the async scraper"""
    scraper = REIScraper(headless=True)
    return asyncio.run(scraper.scrape(state, sources, network, max_results))


if __name__ == '__main__':
    # Test the scraper
    async def test():
        async with HealthgradesScraper(headless=False) as scraper:
            providers = await scraper.search_providers('CA', max_results=5)
            for p in providers:
                print(f"{p.name} - {p.city}, {p.state}")
                print(f"  Score: {p.healthgrades_score}, Reviews: {p.review_count}")
                print(f"  URL: {p.profile_url}")
                print()
    
    asyncio.run(test())
