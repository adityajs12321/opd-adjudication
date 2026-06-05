import requests
import json
import traceback

test_cases = json.load(open("../test_cases.json"))

for test_case in test_cases["test_cases"]:
    try:
        case_id = test_case["case_id"].lower()
        prescription = f"../generated_documents/test_cases/{case_id}/prescription.png"
        bill = f"../generated_documents/test_cases/{case_id}/medical_bill.png"

        files = {}
        import os
        if os.path.exists(prescription):
            files["prescription"] = open(prescription, "rb")
        if os.path.exists(bill):
            files["medical_bill"] = open(bill, "rb")
        
        data = {
            "member_id": test_case["input_data"]["member_id"],
            "claimed_amount": test_case["input_data"]["claim_amount"],
        }

        response = requests.post("http://localhost:8000/adjudicate-documents", data=data, files=files)
        print(f"Test case {case_id}: {response.json()}")
    except Exception as e:
        print(f"Error on {case_id}: {str(e)}")
