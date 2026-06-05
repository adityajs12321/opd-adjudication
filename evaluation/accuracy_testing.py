import requests
import json
import os

test_cases = json.load(open("../test_cases.json"))

# adjudicate-documents endpoint:
# def adjudicate_documents(
#     member_id: str = Form(...),
#     claimed_amount: float = Form(0),
#     prescription: UploadFile | None = File(None),
#     medical_bill: UploadFile | None = File(None),
# ):

denom = 10
num = 0
rejection_codes_num = 0
rejection_codes_denom = 0

for test_case in test_cases["test_cases"][0:1]:
    case_id = test_case["case_id"].lower()
    prescription = "../generated_documents/test_cases/{case_id}/prescription.png".format(case_id=case_id)
    bill = "../generated_documents/test_cases/{case_id}/medical_bill.png".format(case_id=case_id)

    files = {}
    if os.path.exists(prescription):
        files["prescription"] = open(prescription, "rb")
    if os.path.exists(bill):
        files["medical_bill"] = open(bill, "rb")

    data = {
        "member_id": test_case["input_data"]["member_id"],
        "claimed_amount": test_case["input_data"]["claim_amount"],
    }

    response = requests.post("http://localhost:8000/adjudicate-documents", data=data, files=files)
    response = response.json()
    if test_case["expected_output"]["decision"] == response["decision"]["decision"]:
        num += 1
    if test_case["expected_output"]["decision"] == "REJECTED":
        rejection_codes_denom += len(test_case["expected_output"]["rejection_reasons"])
        n = len(response["decision"]["rejection_reasons"])
        for i in range(n):
            if response["decision"]["rejection_reasons"][i] in test_case["expected_output"]["rejection_reasons"]:
                rejection_codes_num += 1
    print(f"Expected decision: {test_case['expected_output']['decision']}, Got: {response['decision']['decision']}")
    print(response['decision']['notes'])
    if test_case["expected_output"]["decision"] == "REJECTED": print(f"Expected rejection reasons: {test_case['expected_output']['rejection_reasons']}, Got: {response['decision']['rejection_reasons']}")
    print(f"test case {case_id} over")


print(f"Accuracy: {num}/{denom}")
print(f"Rejection Codes Accuracy: {rejection_codes_num}/{rejection_codes_denom}")