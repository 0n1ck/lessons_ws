from selenium.webdriver import Firefox, FirefoxOptions
from selenium.webdriver.common.by import By

def get_data(url)->list:
    browser_options = FirefoxOptions()
    browser_options.headless = True

    driver = Firefox(options=FirefoxOptions)
    driver.get(url)

    data = driver.page_source

    driver.quit()
    
    return data

def main():
    data = get_data()




if __name__ == '__main__':
    main()