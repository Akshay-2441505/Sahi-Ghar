"""Synthetic registration-application text that mirrors the layout of the real one (all people and numbers are invented).

The real documents also carry bank account numbers, phone numbers, emails and Aadhaar numbers, so the sample includes
fake ones of each: the extractor must drop them all.
"""
import base64

COMPANY = """MAHA-RERA Application
General Information
Organization
Address Details
Organization Contact Details
Past Experience Details
Member Information
Member Name Designation PAN No. VIEW
Asha Rao Authorized Signatory BBBPB1234B
 View Details
Vikram Sethi Director CCCPC1234C
 View Details
Information Type Other Than Individual
Application Number REA50000000001
Payment Date 27/07/2017
Total Amount Paid by User 81740.50
Name Acme Builders Pvt Ltd PAN Number AAAPA1234A
Organization Type Company
Description For Other Type
Organization
NA
Do you have any Past Experience ? Yes
Block Number Acme House Building Name Acme Tech Park
Street Name Ring Road Locality Vimannagar
Land mark Opp City Mall State Maharashtra
Division Pune District Pune
Taluka Haveli Village VIMANNAGAR
Pin Code 411014
Name of Contact Person Meena Kulkarni Designation of Contact Person Manager
Office Number 9876543210
Fax Number Email ID meena@acme.example
Secondary Mobile Number 9123456789
Website URL
Sr.No.
Project
Name
Type of
Project Others
Land
Area(In
Sq mtrs) Address Total Cost CTS Number
Number of
Buildings/Plot
Number of
Apartments
Original
Proposed
Date of
Completion
Actual Date
of
Completion
1 Willow Court Residential NA 19191.64 Baner 661331589 S No 13, Hissa No 3,4,5 6 160 2013-11-30 2015-04-27
2 Eco Tower Commercial NA 4862.32 Baner 213786447 3/13/1, 3/13/2 1 19 2014-08-20 2016-11-29
3 Forest
County
Residential NA 207720 Kharadi 900000001 Sector No 1 of S No 40, S No
41 and S No 59
18 809 2017-12-31 2017-04-10
Project
FSI Details
Bank Details
Co-Promoter Details
Project Details
Name Proposed Booked WorkDone(In %)
Project Name Windermere Phase 1 Project Status On-Going Project
Proposed Date of Completion 16/12/2016 Revised Proposed Date of
Completion
31/12/2018
Litigations related to the project ? Yes Project Type Residential
Bank Name Example Bank of India Bank A/c Number 644601010050211
IFSC Code EXAM0564460 Branch Name Pune
Aadhar Number 123412341234
"""

INDIVIDUAL = """MAHA-RERA Application
General Information
Individual
Address For Official Communication
Contact Details
Past Experience Details
Information Type Individual
Application Number REA51700006804
First Name RAVI Middle Name
Last Name PATIL PAN Number DDDPD1234D
Father Full Name LATE SHRI KISHAN PATIL Aadhar Number 432143214321
Do you have any Past
Experience ?
Yes
House Number 20, GR FLOOR Building Name SHANTI APARTMENTS
Street Name PLOT NO-10 Locality VASHI NAVI MUMBAI
Landmark NEAR TEMPLE State Maharashtra
Division Konkan District Thane
Taluka Thane Village Navi Mumbai (M Corp.)
Pin Code 400703
Mobile Number 9000000002
Email ID
ravi@example.test
Sr.No.
Project
Name
Type of
Project Others
Land
Area(In
Sq
mtrs) Address
Total
Cost
CTS
Number
Number of
Buildings/Plot
Number of
Apartments
Original
Proposed
Date of
Completion
Actual Date
of
Completion
1 Lotus
Meadows
Residential NA 850 Plot No
75
Sector
900000002 75 1 24 2015-03-10 2015-01-10
Sr.No.
Project
Name
Project Status Completed Proposed Date of Completion 10/03/2015
Litigations related to the project ? No
"""

FORBIDDEN = ("AAAPA1234A", "BBBPB1234B", "CCCPC1234C", "DDDPD1234D", "9876543210", "9123456789", "meena@acme.example",
             "644601010050211", "EXAM0564460", "123412341234", "432143214321", "ravi@example.test", "Asha Rao", "Vikram Sethi",
             "Meena Kulkarni", "SHANTI APARTMENTS", "RAVI", "PATIL", "KISHAN")


def make_pdf(text: str) -> bytes:
    """A minimal one-page PDF whose text layer is `text` (enough for pypdf's text extraction)."""
    def esc(line: str) -> str:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    body = "BT /F1 8 Tf 10 780 Td 9 TL\n" + "\n".join(f"({esc(line)}) Tj T*" for line in text.splitlines()) + "\nET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def application_html(text: str) -> bytes:
    """What the site's document endpoint returns: HTML wrapping the PDF as base64."""
    encoded = base64.b64encode(make_pdf(text)).decode()
    return f'<div id="setDataDocument"><object data=data:application/pdf;base64,{encoded} type=application/pdf></object></div>'.encode()


# An LLP: a different member table header, the partner list in a second table further down, organization type "Others".
LLP = """MAHA-RERA Application
General Information
Past Experience Details
Other Organization Type Member Information
Name Member Type PAN No. VIEW
Asha Rao Individual BBBPB1234B View
Information Type Other Than Individual
Application Number REA50000000002
Total Amount Paid by User 1000.00 Name Acme LLP PAN Number AAAPA1234A
Organization Type Others Description For Other Type
Do you have any Past Experience ? No
Block Number 5 Building Name Acme Chambers
Street Name Main Road Locality Camp
Division Pune District Pune
Taluka Haveli Village CAMP
Pin Code 411001
Name of Contact Person Asha Rao Designation of Contact Person Designated Partner
Vikram Sethi Individual CCCPC1234C View
Meena Kulkarni Others EEEPE1234E View
Asha Rao Individual BBBPB1234B View
"""

# Newer applications show PANs masked (only the last characters): they identify nobody, so they must never become tokens.
MASKED = COMPANY.replace("PAN Number AAAPA1234A", "PAN Number xxxxxx234A").replace("BBBPB1234B", "xxxxxx234B").replace("CCCPC1234C", "xxxxxx234C")

FORBIDDEN_LLP = ("AAAPA1234A", "BBBPB1234B", "CCCPC1234C", "EEEPE1234E", "Vikram Sethi", "Meena Kulkarni", "Asha Rao")
