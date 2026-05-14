#!/usr/bin/env python3
"""
REI Scan - Provider Scraper Web Application
Hosted at reiscan.openclapp.com
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from dataclasses import dataclass
from typing import List, Optional, Dict
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

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
            'source': self.source
        }


from scraper import scrape_providers, Provider as ScraperProvider

class RealScraper:
    """Real scraper using Playwright"""
    
    def scrape(self, state: str, sources: List[str], network: Optional[str] = None) -> List[Provider]:
        """Scrape using real implementation"""
        # Convert scraper Provider to app Provider
        raw_providers = scrape_providers(state, sources, network, max_results=50)
        
        providers = []
        for p in raw_providers:
            providers.append(Provider(
                name=p.name,
                clinic=p.clinic,
                address=p.address,
                city=p.city,
                state=p.state,
                zip_code=p.zip_code,
                phone=p.phone,
                specialties=p.specialties,
                healthgrades_score=p.healthgrades_score,
                review_count=p.review_count,
                cigna_in_network=p.cigna_in_network,
                cigna_plans=p.cigna_plans,
                source=p.source
            ))
        
        return providers

class MockScraper:
    """Mock scraper for testing - fallback if real scraper fails"""
    
    def scrape(self, state: str, sources: List[str], network: Optional[str] = None) -> List[Provider]:
        """Return mock data for testing"""
        mock_providers = [
            Provider(
                name="Dr. Sarah Johnson, MD",
                clinic="Fertility Center of Excellence",
                address="123 Medical Plaza Dr",
                city="Los Angeles",
                state=state,
                zip_code="90025",
                phone="(310) 555-0123",
                specialties=["Reproductive Endocrinology", "Infertility"],
                healthgrades_score=4.8,
                review_count=127,
                cigna_in_network=True,
                cigna_plans=["Cigna PPO", "Cigna Open Access Plus"],
                source="healthgrades"
            ),
            Provider(
                name="Dr. Michael Chen, MD",
                clinic="Pacific Fertility Institute",
                address="456 Healthcare Blvd",
                city="Santa Monica",
                state=state,
                zip_code="90401",
                phone="(310) 555-0456",
                specialties=["Reproductive Endocrinology", "IVF"],
                healthgrades_score=4.5,
                review_count=89,
                cigna_in_network=False,
                cigna_plans=[],
                source="healthgrades"
            ),
            Provider(
                name="Dr. Emily Rodriguez, MD",
                clinic="Advanced Reproductive Care",
                address="789 Wellness Way",
                city="Beverly Hills",
                state=state,
                zip_code="90210",
                phone="(310) 555-0789",
                specialties=["Reproductive Endocrinology", "PCOS", "Endometriosis"],
                healthgrades_score=4.2,
                review_count=56,
                cigna_in_network=None,
                cigna_plans=[],
                source="healthgrades"
            ),
            Provider(
                name="Dr. James Wilson, MD",
                clinic="Wilson Fertility Specialists",
                address="321 Hope Street",
                city="Pasadena",
                state=state,
                zip_code="91101",
                phone="(626) 555-0321",
                specialties=["Reproductive Endocrinology", "Male Infertility"],
                healthgrades_score=4.9,
                review_count=203,
                cigna_in_network=True,
                cigna_plans=["Cigna PPO", "Cigna HMO", "Cigna SureFit"],
                source="healthgrades"
            ),
            Provider(
                name="Dr. Lisa Park, MD",
                clinic="Park Reproductive Medicine",
                address="654 Miracle Mile",
                city="Los Angeles",
                state=state,
                zip_code="90036",
                phone="(323) 555-0654",
                specialties=["Reproductive Endocrinology", "Egg Freezing"],
                healthgrades_score=3.8,
                review_count=34,
                cigna_in_network=False,
                cigna_plans=[],
                source="healthgrades"
            )
        ]
        
        # Filter by network if specified
        if network == 'cigna':
            mock_providers = [p for p in mock_providers if p.cigna_in_network]
        
        return mock_providers


@app.route('/')
def index():
    """Homepage - redirect to search"""
    return redirect(url_for('search'))


@app.route('/search')
def search():
    """Search form page"""
    return render_template('search.html')


@app.route('/search', methods=['POST'])
def do_search():
    """Handle search form submission"""
    state = request.form.get('state', '').upper()
    sources = request.form.getlist('sources')
    network = request.form.get('network')
    
    if not state:
        flash('Please select a state', 'error')
        return redirect(url_for('search'))
    
    if not sources:
        flash('Please select at least one source', 'error')
        return redirect(url_for('search'))
    
    # Perform scrape
    try:
        # Try real scraper first
        scraper = RealScraper()
        providers = scraper.scrape(state, sources=sources, network=network)
    except Exception as e:
        logger.error(f"Real scraper failed: {e}, falling back to mock")
        scraper = MockScraper()
        providers = scraper.scrape(state, sources=sources, network=network)
        
        # Store results in session
        session['results'] = [p.to_dict() for p in providers]
        session['search_params'] = {
            'state': state,
            'sources': sources,
            'network': network
        }
        
        return redirect(url_for('results'))
        
    except Exception as e:
        flash(f'Error during search: {str(e)}', 'error')
        return redirect(url_for('search'))


@app.route('/results')
def results():
    """Display search results"""
    providers_data = session.get('results', [])
    search_params = session.get('search_params', {})
    
    # Convert dicts back to Provider objects
    providers = [Provider(**p) for p in providers_data]
    
    return render_template('results.html',
                         providers=providers,
                         search_params=search_params,
                         count=len(providers))


@app.route('/api/search', methods=['POST'])
def api_search():
    """API endpoint for programmatic access"""
    data = request.get_json()
    state = data.get('state', '').upper()
    sources = data.get('sources', ['healthgrades'])
    network = data.get('network')
    
    if not state:
        return jsonify({'error': 'State is required'}), 400
    
    try:
        scraper = MockScraper()  # Replace with real scraper
        providers = scraper.scrape(state, sources=sources, network=network)
        
        return jsonify({
            'success': True,
            'count': len(providers),
            'providers': [p.to_dict() for p in providers]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'reiscan',
        'version': '1.0.0'
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
