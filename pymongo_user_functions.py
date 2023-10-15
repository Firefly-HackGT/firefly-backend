from pymongo import MongoClient
def get_database():
 
   # Provide the mongodb atlas url to connect python to mongodb using pymongo
   CONNECTION_STRING = "mongodb+srv://Stephan:68noDnGIBUnAjrao@firefly.mkpxt60.mongodb.net/"
 
   # Create a connection using MongoClient. You can import MongoClient or use pymongo.MongoClient
   client = MongoClient(CONNECTION_STRING)
 
   # Create the database for our example (we will use the same database throughout the tutorial
   return client['Users']
  
# This is added so that many files can reuse the function get_database()
if __name__ == "__main__":   
  
   # Get the database
   dbname = get_database()

def get_student_lectures(name):
   student = get_database()["Students"].find({"name" : name})[0]
   return student["lectures"]
   
def student_exists(name):
   try:
      student = get_database()["Students"].find({"name" : name})[0]
   except IndexError:
      return False
   return True

def add_student_lecture(name, lecture):
   cname = get_database()["Students"]
   updateResult = cname.update_one( 
      { "name": name },
      { "$addToSet": { "lectures": lecture } }
   )
   if updateResult.matched_count == 0:
        new_student = {
        "name" : name,
        "lectures" : [lecture]
        }
        cname.insert_one(new_student)
   

def get_professor_lectures(name):
   professor = get_database()["Professors"].find({"name" : name})[0]
   return professor["lectures"]
   
def professor_exists(name):
   try:
      professor = get_database()["Professors"].find({"name" : name})[0]
   except IndexError:
      return False
   return True

def add_professor_lecture(name, lecture):
   cname = get_database()["Professors"]
   updateResult = cname.update_one( 
      { "name": name },
      { "$addToSet": { "lectures": lecture } }
   )
   if updateResult.matched_count == 0:
      new_professor = {
         "name" : name,
         "lectures" : [lecture]
      }
      cname.insert_one(new_professor)